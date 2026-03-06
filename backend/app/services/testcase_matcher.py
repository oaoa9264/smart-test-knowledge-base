import json
import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.models.entities import RuleNode
from app.services.llm_client import LLMClient
from app.services.prompts.testcase_match import MATCH_SYSTEM_PROMPT, MATCH_USER_TEMPLATE
from app.services.testcase_importer import ParsedTestCase


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]+")
_VALID_CONFIDENCE = {"high", "medium", "low", "none"}
_CHINESE_ONLY_PATTERN = re.compile(r"^[\u4e00-\u9fff]+$")
_COVERABLE_TYPES = {"action", "branch", "exception"}
_EXCLUDED_MATCH_TYPES = {"root"}


@dataclass
class MatchResult:
    case_index: int
    matched_node_ids: List[str]
    confidence: str
    reason: str


class TestCaseMatcher:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        top_k: Optional[int] = None,
        batch_size: Optional[int] = None,
    ):
        self._llm_client = llm_client
        self._llm_provider: Optional[str] = None
        self.top_k = top_k or int(os.getenv("TESTCASE_MATCH_TOP_K", "30"))
        self.batch_size = batch_size or int(os.getenv("TESTCASE_MATCH_BATCH_SIZE", "6"))

    def match_cases(
        self,
        parsed_cases: Sequence[ParsedTestCase],
        rule_nodes: Sequence[RuleNode],
    ) -> Tuple[List[MatchResult], str]:
        self._llm_provider = None
        if not parsed_cases:
            return [], "mock_fallback"

        if not rule_nodes:
            return [
                MatchResult(case_index=index, matched_node_ids=[], confidence="none", reason="当前需求暂无规则节点")
                for index, _ in enumerate(parsed_cases)
            ], "mock_fallback"

        try:
            results = self._match_with_llm(parsed_cases=parsed_cases, rule_nodes=rule_nodes)
            return results, "llm"
        except Exception:
            fallback_results = self._match_with_keyword_fallback(parsed_cases=parsed_cases, rule_nodes=rule_nodes)
            return fallback_results, "mock_fallback"

    def get_llm_provider(self) -> Optional[str]:
        return self._llm_provider

    def _get_llm(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def _match_with_llm(
        self,
        parsed_cases: Sequence[ParsedTestCase],
        rule_nodes: Sequence[RuleNode],
    ) -> List[MatchResult]:
        llm = self._get_llm()
        all_node_ids = {node.id for node in rule_nodes}
        case_candidates: List[List[RuleNode]] = [
            self._select_candidates(case.raw_text, rule_nodes, top_k=self.top_k) for case in parsed_cases
        ]

        default_results: Dict[int, MatchResult] = {
            index: MatchResult(case_index=index, matched_node_ids=[], confidence="none", reason="未命中规则节点")
            for index in range(len(parsed_cases))
        }

        for batch_start in range(0, len(parsed_cases), self.batch_size):
            batch_indexes = list(range(batch_start, min(batch_start + self.batch_size, len(parsed_cases))))

            candidate_union: Dict[str, RuleNode] = {}
            for index in batch_indexes:
                for node in case_candidates[index]:
                    candidate_union[node.id] = node

            if not candidate_union:
                continue

            candidate_ids = set(candidate_union.keys())
            nodes_payload = [
                {"id": node.id, "content": node.content, "node_type": str(node.node_type)}
                for node in candidate_union.values()
            ]
            cases_payload = [
                {
                    "case_index": index,
                    "title": parsed_cases[index].title,
                    "steps": parsed_cases[index].steps,
                    "expected_result": parsed_cases[index].expected_result,
                    "raw_text": parsed_cases[index].raw_text,
                }
                for index in batch_indexes
            ]
            prompt = MATCH_USER_TEMPLATE.format(
                nodes_json=json.dumps(nodes_payload, ensure_ascii=False),
                cases_json=json.dumps(cases_payload, ensure_ascii=False),
            )
            payload = llm.chat_with_json(system_prompt=MATCH_SYSTEM_PROMPT, user_prompt=prompt)
            self._llm_provider = self._resolve_provider_from_llm(llm) or self._llm_provider
            matches = payload.get("matches")
            if not isinstance(matches, list):
                continue

            for item in matches:
                case_index = item.get("case_index")
                if not isinstance(case_index, int):
                    continue
                if case_index not in default_results:
                    continue
                raw_ids = item.get("matched_node_ids", [])
                if not isinstance(raw_ids, list):
                    raw_ids = []
                filtered_ids = [
                    node_id for node_id in raw_ids if isinstance(node_id, str) and node_id in candidate_ids and node_id in all_node_ids
                ]
                confidence = str(item.get("confidence", "none")).lower()
                if confidence not in _VALID_CONFIDENCE:
                    confidence = "none"
                if not filtered_ids:
                    confidence = "none"
                reason = str(item.get("reason", "")).strip() or "LLM 未返回匹配理由"
                default_results[case_index] = MatchResult(
                    case_index=case_index,
                    matched_node_ids=list(dict.fromkeys(filtered_ids)),
                    confidence=confidence,
                    reason=reason,
                )

        return [default_results[index] for index in range(len(parsed_cases))]

    @staticmethod
    def _resolve_provider_from_llm(llm: object) -> Optional[str]:
        getter = getattr(llm, "get_last_provider", None)
        if not callable(getter):
            return None
        provider = getter(method_name="chat_with_json")
        if provider:
            return str(provider).strip().lower()
        return None

    def _match_with_keyword_fallback(
        self,
        parsed_cases: Sequence[ParsedTestCase],
        rule_nodes: Sequence[RuleNode],
    ) -> List[MatchResult]:
        matchable_nodes = [n for n in rule_nodes if self._node_type_str(n) not in _EXCLUDED_MATCH_TYPES]
        if not matchable_nodes:
            matchable_nodes = list(rule_nodes)
        results: List[MatchResult] = []
        for index, case in enumerate(parsed_cases):
            scored = self._score_nodes(case.raw_text, matchable_nodes)
            if not scored or scored[0][1] <= 0:
                results.append(
                    MatchResult(
                        case_index=index,
                        matched_node_ids=[],
                        confidence="none",
                        reason="关键词兜底未命中，请手动绑定节点",
                    )
                )
                continue

            top_score = scored[0][1]
            matched = [node.id for node, score in scored[:3] if score >= max(1, int(top_score * 0.6))]
            if top_score >= 4:
                confidence = "high"
            elif top_score >= 2:
                confidence = "medium"
            else:
                confidence = "low"

            results.append(
                MatchResult(
                    case_index=index,
                    matched_node_ids=matched,
                    confidence=confidence,
                    reason="基于关键词重合度进行兜底匹配",
                )
            )
        return results

    def _select_candidates(
        self,
        case_text: str,
        nodes: Sequence[RuleNode],
        top_k: int,
    ) -> List[RuleNode]:
        matchable = [n for n in nodes if self._node_type_str(n) not in _EXCLUDED_MATCH_TYPES]
        if not matchable:
            matchable = list(nodes)
        scored = self._score_nodes(case_text, matchable)
        selected = [node for node, _ in scored if _ > 0][:top_k]
        if selected:
            return selected
        return list(matchable[:top_k])

    def _score_nodes(self, case_text: str, nodes: Sequence[RuleNode]) -> List[Tuple[RuleNode, int]]:
        case_tokens = self._tokenize(case_text)
        scored: List[Tuple[RuleNode, int]] = []
        for node in nodes:
            node_tokens = self._tokenize(node.content)
            overlap = len(case_tokens & node_tokens)
            substring_bonus = 0
            if case_text and node.content and node.content in case_text:
                substring_bonus = 2
            type_bonus = 1 if self._node_type_str(node) in _COVERABLE_TYPES else 0
            scored.append((node, overlap + substring_bonus + type_bonus))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored

    @staticmethod
    def _node_type_str(node: RuleNode) -> str:
        nt = getattr(node, "node_type", None)
        if nt is None:
            return ""
        return nt.value if hasattr(nt, "value") else str(nt)

    @staticmethod
    def _tokenize(text: str) -> Set[str]:
        tokens: Set[str] = set()
        for raw in _TOKEN_PATTERN.findall(text or ""):
            token = raw.lower()
            if not token:
                continue
            tokens.add(token)
            if _CHINESE_ONLY_PATTERN.match(token) and len(token) >= 2:
                for index in range(len(token) - 1):
                    tokens.add(token[index : index + 2])
        return tokens
