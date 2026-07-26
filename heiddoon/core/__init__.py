"""The five mechanics, one module each, mapped to the features in the design doc."""

from .bouncer import ask_question, break_granted_line, grade_answer
from .contract import compile_contract, load_contract, save_contract
from .diff import count_words, judge_delta, net_word_delta, unified_diff
from .receipt import compute_focus_score, make_receipt
from .verdict import judge_frame

__all__ = [
    "ask_question",
    "break_granted_line",
    "compile_contract",
    "compute_focus_score",
    "count_words",
    "grade_answer",
    "judge_delta",
    "judge_frame",
    "load_contract",
    "make_receipt",
    "net_word_delta",
    "save_contract",
    "unified_diff",
]
