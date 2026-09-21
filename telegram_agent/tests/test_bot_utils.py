"""Tests for ``telegram_agent/src/bot/utils.py``."""

from telegram_agent.src.bot.utils import (
    fixed_telegram,
    logify_telegram,
    progress_bar,
    reply_markup,
    strip_html_tags,
    strip_rich_images,
    unpack_user,
)
from telegram_agent.tests.fakes import make_message


class TestUnpackUser:
    def test_username_preferred(self):
        msg = make_message(
            user_id=7,
            **{
                "from": {
                    "id": 7,
                    "is_bot": False,
                    "first_name": "Tester",
                    "username": "testy",
                }
            },
        )
        assert unpack_user(msg) == ("testy", "Tester")

    def test_username_falls_back_to_id(self):
        msg = make_message(user_id=7)
        assert unpack_user(msg) == ("7", "Tester")

    def test_missing_sender(self):
        msg = make_message(from_user=False)
        assert unpack_user(msg) == ("?", "Unknown")


class TestFixedTelegram:
    def test_bold_italic_underline_strike(self):
        out = fixed_telegram(None, "**b** *i* __u__ ~~s~~")
        assert out == "<b>b</b> <i>i</i> <u>u</u> <s>s</s>"

    def test_inline_code_and_code_block(self):
        out = fixed_telegram(None, "`a < b`\n\n```python\nx = 1 < 2\n```")
        assert "<code>a &lt; b</code>" in out
        assert '<pre><code class="language-python">' in out
        assert "x = 1 &lt; 2" in out

    def test_code_block_without_language(self):
        out = fixed_telegram(None, "```\nplain\n```")
        assert "<pre>\nplain\n</pre>" in out

    def test_links_spoilers_and_marks(self):
        out = fixed_telegram(None, "[t](https://e.co) ||secret|| ==hl==", classic=False)
        assert '<a href="https://e.co">t</a>' in out
        assert "<tg-spoiler>secret</tg-spoiler>" in out
        assert "<mark>hl</mark>" in out

    def test_classic_mode_downgrades_mark(self):
        assert "<u>hl</u>" in fixed_telegram(None, "==hl==")

    def test_ampersand_escaping_preserves_entities(self):
        out = fixed_telegram(None, "a & b &amp; c")
        assert "&amp;" in out
        assert out.count("&amp;amp;") == 0

    def test_heading_and_hr(self):
        out = fixed_telegram(None, "## Title\n\n---\nbody", classic=False)
        assert "<h2>Title</h2>" in out
        assert "<hr>" in out

    def test_classic_mode_downgrades_heading_and_hr(self):
        out = fixed_telegram(None, "## Title\n\n---\nbody")
        assert "<b>Title</b>" in out
        assert "———" in out
        assert "<h2>" not in out

    def test_table_conversion(self):
        out = fixed_telegram(None, "| a | b |\n| --- | --- |\n| 1 | 2 |", classic=False)
        assert "<table>" in out
        assert "<th>a</th>" in out
        assert "<td>1</td>" in out

    def test_table_without_data_rows(self):
        out = fixed_telegram(None, "| a | b |\n| --- | --- |")
        assert "<table>" not in out

    def test_unordered_and_ordered_lists(self):
        out = fixed_telegram(None, "- one\n- two", classic=False)
        assert "<ul><li>one</li><li>two</li></ul>" in out
        out = fixed_telegram(None, "1. first\n2. second", classic=False)
        assert "<ol><li>first</li><li>second</li></ol>" in out

    def test_task_list_checkboxes(self):
        out = fixed_telegram(None, "- [x] done\n- [ ] todo", classic=False)
        assert '<input type="checkbox" checked/>done' in out
        assert '<input type="checkbox"/>todo' in out

    def test_blockquote(self):
        assert "<blockquote>quoted</blockquote>" in fixed_telegram(None, "> quoted")

    def test_classic_mode_downgrades_rich_tags(self):
        out = fixed_telegram(None, "# H\n\n==hl==\n\n- item\n\n---")
        assert "<h1>" not in out
        assert "<mark>" not in out
        assert "<ul>" not in out
        assert "<b>H</b>" in out
        assert "<u>hl</u>" in out
        assert "• item" in out
        assert "———" in out

    def test_rich_mode_keeps_rich_tags(self):
        out = fixed_telegram(None, "# H\n\n- item", classic=False)
        assert "<h1>H</h1>" in out
        assert "<ul><li>item</li></ul>" in out

    def test_nested_lists_flatten_innermost_first(self):
        out = fixed_telegram(None, "- a\n  - b")
        assert "<ul>" not in out

    def test_images(self):
        out = fixed_telegram(None, '![alt](https://e.co/i.png "cap")', classic=False)
        assert (
            '<figure><img src="https://e.co/i.png"/><figcaption>cap</figcaption></figure>'
            in out
        )
        out = fixed_telegram(None, "![alt](https://e.co/i.png)", classic=False)
        assert '<img src="https://e.co/i.png"/>' in out
        # Non-http images are dropped
        assert "data:image" not in fixed_telegram(
            None, "![x](data:image/png;base64,AA)"
        )

    def test_raw_angle_brackets_escaped(self):
        assert "a &lt; b" in fixed_telegram(None, "a < b")
        assert "1 &gt; 0" in fixed_telegram(None, "1 > 0")
        # Inside fenced code everything is escaped, or a literal </pre>
        # would close the enclosing block.
        out = fixed_telegram(None, "```\n</pre>\n```")
        assert "&lt;/pre&gt;" in out

    def test_alphabetic_tag_like_text_escaped_as_literal(self):
        # Unknown tag-shaped text is escaped to literal text: Telegram's HTML
        # parse mode rejects unsupported tags outright (400 unsupported start
        # tag), so pass-through was never safe (leaked <tool_call> incident).
        out = fixed_telegram(None, "a <notatag> b")
        assert "&lt;notatag&gt;" in out
        assert "<notatag>" not in out

    def test_blank_lines_collapsed(self):
        assert "\n\n\n" not in fixed_telegram(None, "a\n\n\n\nb")

    def test_ordered_list_conversion_to_text(self):
        out = fixed_telegram(None, "1. a\n2. b")
        # classic mode downgrades to numbered text
        assert "<ol>" not in out
        assert "1. a" in out
        assert "2. b" in out


class TestStripRichImages:
    def test_removes_media_and_unwraps_figures(self):
        html = (
            '<figure><img src="http://x/i.png"/><figcaption>cap</figcaption></figure>'
        )
        assert strip_rich_images(html) == "cap"

    def test_collapses_blank_lines(self):
        assert strip_rich_images("a\n\n\n\nb") == "a\n\nb"

    def test_media_open_tags_removed(self):
        # Opening/self-closing media tags are stripped; closing tags of
        # non-figure elements are left to Telegram's parser.
        html = '<img src="i.png"/>a<tg-collage/>b'
        assert strip_rich_images(html) == "ab"


class TestStripHtmlTags:
    def test_leaves_entities_escaped(self):
        assert strip_html_tags("<b>a</b> &amp; b") == "a &amp; b"


class TestLogifyTelegram:
    def test_string_content_and_label(self):
        out = logify_telegram(None, "My Agent", "line")
        assert out.startswith('<pre><code class="language-My-Agent">')
        assert "line" in out

    def test_list_content_and_escaping(self):
        out = logify_telegram(None, None, ["a < b", "c"])
        assert "a &lt; b" in out
        assert '<code class="language-Logs">' in out

    def test_empty_content(self):
        assert logify_telegram(None, "A", []) == ""
        assert logify_telegram(None, "A", "") == ""

    def test_null_bytes_removed(self):
        assert "\x00" not in logify_telegram(None, "A", "a\x00b")


class TestProgressBar:
    def test_bounds(self):
        assert progress_bar(0, 100).endswith("  0.0%")
        assert progress_bar(50, 100).endswith(" 50.0%")
        assert progress_bar(100, 100).endswith("100.0%")

    def test_zero_total_treated_as_one(self):
        assert "100.0%" in progress_bar(1, 0)

    def test_custom_size(self):
        assert len(progress_bar(1, 2, size=10).split(" ")[0]) == 10


class TestReplyMarkup:
    def test_keyboard_has_pagination_buttons(self):
        markup = reply_markup(1, 5)
        datas = [b.callback_data for row in markup.keyboard for b in row]
        assert datas == ["first", "prev", "none", "next", "last"]
        labels = [b.text for row in markup.keyboard for b in row]
        assert "2/5" in labels


class TestFixedTelegramUnknownTags:
    """Model-emitted non-Telegram markup must stay valid Telegram HTML."""

    def test_unknown_tags_escaped_as_literal_text(self):
        out = fixed_telegram(None, "<tool_call>update_task</tool_call>")
        assert "&lt;tool_call&gt;update_task&lt;/tool_call&gt;" in out
        assert "<tool_call>" not in out

    def test_leaked_glm_markup_never_reaches_the_wire_untouched(self):
        raw = (
            "<tool_call>update_task<arg_key>status</arg_key>"
            "<arg_value>done</arg_value></tool_call>"
        )
        out = fixed_telegram(None, raw)
        assert "<tool_call>" not in out
        assert "<arg_key>" not in out
        assert "update_task" in out  # content stays readable

    def test_supported_tags_preserved(self):
        out = fixed_telegram(None, "keep <b>bold</b> and <code>x</code> inline")
        assert "<b>bold</b>" in out
        assert "<code>x</code>" in out

    def test_rich_tags_preserved_in_rich_mode(self):
        out = fixed_telegram(None, "<h1>Title</h1>", classic=False)
        assert "<h1>Title</h1>" in out

    def test_rich_tags_still_sanitized_in_classic_mode(self):
        out = fixed_telegram(None, "<h1>Title</h1>")
        assert "<h1>" not in out
        assert "<b>Title</b>" in out

    def test_classic_keeps_tg_time(self):
        # tg-time joined the official HTML parse mode list (Bot API 10.3).
        out = fixed_telegram(None, 'at <tg-time unix="1">22:45</tg-time> sharp')
        assert '<tg-time unix="1">22:45</tg-time>' in out

    def test_classic_unwraps_rich_only_tags(self):
        out = fixed_telegram(None, "a <p>para</p> b and <sub>x</sub>")
        assert "<p>" not in out
        assert "<sub>" not in out
        assert "para" in out
        assert "x" in out

    def test_classic_unwraps_interaction_tags(self):
        out = fixed_telegram(
            None, '<tg-button type="url" url="https://x">go</tg-button>'
        )
        assert "<tg-button" not in out
        assert "go" in out

    def test_classic_converts_br_to_newline(self):
        out = fixed_telegram(None, "one<br>two")
        assert "<br" not in out
        assert "one\ntwo" in out

    def test_rich_keeps_sub_sup_and_media_tags(self):
        out = fixed_telegram(None, "<sub>1</sub><sup>2</sup>", classic=False)
        assert "<sub>1</sub>" in out
        assert "<sup>2</sup>" in out

    def test_unknown_tags_escaped_in_both_modes(self):
        raw = "<tool_call>update_task</tool_call>"
        assert "&lt;tool_call&gt;" in fixed_telegram(None, raw)
        assert "&lt;tool_call&gt;" in fixed_telegram(None, raw, classic=False)
