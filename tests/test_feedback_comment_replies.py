"""反馈中心：回复评论必须紧跟它所属的那一楼（而不是落到列表末尾）。

回归背景：评论按 id 升序平铺渲染，回复虽然带着 parent_comment_id、也写了 data-parent，
但排到了整段评论的最后；当父评论后面还有别的楼时，回复看上去就挂到了最新一楼。
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'js' / 'feedback_center.js').read_text(encoding='utf-8')
CSS = (ROOT / 'static' / 'css' / 'feedback_center.css').read_text(encoding='utf-8')
VERSION = (ROOT / 'static_version.txt').read_text(encoding='utf-8')


def _order(comments):
    """复刻 feedback_center.js 里的分组 + 先父后子的渲染顺序。"""
    by_id = {int(c['id']): c for c in comments}
    replies = {}
    tops = []
    for comment in comments:
        parent = comment.get('parent_comment_id')
        parent_id = int(parent) if parent not in (None, '') else 0
        if not parent_id or parent_id not in by_id:
            tops.append(comment)
            continue
        replies.setdefault(parent_id, []).append(comment)

    ordered = []

    def emit(comment, depth):
        ordered.append((int(comment['id']), depth))
        for child in replies.get(int(comment['id']), []):
            emit(child, depth + 1)

    for top in tops:
        emit(top, 0)
    return ordered


def test_reply_is_rendered_right_after_its_parent():
    comments = [
        {'id': 1, 'parent_comment_id': None},
        {'id': 2, 'parent_comment_id': 1},
        {'id': 3, 'parent_comment_id': None},
        {'id': 4, 'parent_comment_id': 3},
        {'id': 5, 'parent_comment_id': None},
    ]
    assert _order(comments) == [(1, 0), (2, 1), (3, 0), (4, 1), (5, 0)]


def test_reply_chain_nests_under_extended_depth():
    comments = [
        {'id': 1, 'parent_comment_id': None},
        {'id': 2, 'parent_comment_id': 1},
        {'id': 3, 'parent_comment_id': 2},
        {'id': 4, 'parent_comment_id': None},
    ]
    # 之前：回复落在最后（3 会排到 4 后面）
    assert _order(comments) == [(1, 0), (2, 1), (3, 2), (4, 0)]


def test_reply_to_hidden_or_missing_parent_falls_back_to_top_level():
    comments = [
        {'id': 1, 'parent_comment_id': None},
        {'id': 2, 'parent_comment_id': 99},
        {'id': 3, 'parent_comment_id': ''},
    ]
    assert _order(comments) == [(1, 0), (2, 0), (3, 0)]


def test_client_builds_a_reply_tree_instead_of_a_flat_list():
    assert 'repliesByParent' in JS
    assert 'topLevelComments' in JS
    assert 'const renderComment = (comment, depth) =>' in JS
    assert 'children.forEach((child) => { html += renderComment(child, depth + 1); });' in JS
    assert 'topLevelComments.forEach((comment) => { commentSection += renderComment(comment, 0); });' in JS
    # 旧的“平铺并靠 parent_comment_id 打类名”写法必须已经消失
    assert 'const isReply = comment.parent_comment_id != null;' not in JS


def test_replies_are_labelled_and_indented():
    assert 'fc-comment-reply-to' in JS
    assert "esc(t('reply_to', '回复'))" in JS
    assert "Math.min(depth, 3) * 22" in JS
    assert '.fc-comment-reply-to' in CSS
    assert '.fc-comment.fc-comment-reply' in CSS


def test_version_bumped_for_this_fix():
    assert VERSION.strip().endswith('-feedback-reply-order-1')
