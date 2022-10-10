from itertools import chain
import json
import re
from typing import Dict, Optional

try:
    import weechat
except ImportError:
    print("This script must be run under WeeChat.")
    print("Get WeeChat now at: http://www.weechat.org/")


SCRIPT_NAME    = "slug_complete"
SCRIPT_AUTHOR  = "SnoopJ"
SCRIPT_VERSION = "1.0"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC    = "Plugin for turning a :slug: into a corresponding text replacement"
SCRIPT_DEFAULT_CONFIG = {
    "cldr_db_file": "/home/snoopjedi/.weechat/python/annotations.json",
    "user_short_names_file": "/home/snoopjedi/.weechat/python/user_short_names.json",
}

weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, '', 'utf-8')
for option, default_value in SCRIPT_DEFAULT_CONFIG.items():
    if not weechat.config_is_set_plugin(option):
        weechat.config_set_plugin(option, default_value)

SCRIPT_CLDR_FILE = weechat.config_get_plugin("cldr_db_file")
SCRIPT_USER_SHORTNAME_FILE = weechat.config_get_plugin("user_short_names_file")

weechat.hook_completion("slug_complete", "Replaces last word in input by its configured value.", "completion_replacer", "")
weechat.hook_modifier("irc_out_privmsg", "modify_message", "")


CODEPOINT = str
SHORT_NAME = str


def cldr_short_names(cldr_file: str, user_aliases_file: Optional[str] = None) -> Dict[SHORT_NAME, CODEPOINT]:
    """
    Helper for working with the Unicode Common Locale Data Registry (CLDR)

    Parameters
    ----------
    cldr_file: str
        Path to the annotations.json defined here (as of CLDR v41):
        https://github.com/unicode-org/cldr-json/blob/main/cldr-json/cldr-annotations-full/annotations/en/annotations.json
    user_aliases_file: str, optional
        Path to a JSON file defining user aliases (a mapping of the form ``{":slug:": "replacement"}``)
    """
    with open(cldr_file, "r") as f:
        data = json.load(f)

    CLDR_DB = data["annotations"]["annotations"]

    result = dict()
    for idx, (codept, metadata) in enumerate(CLDR_DB.items()):
        tts = metadata["tts"][0]
        slug = tts.replace(" ", "-")
        result[f":{slug}:"] = codept

    # Try to load user overrides and update the result with them
    if user_aliases_file:
        try:
            with open(user_aliases_file, "r") as f:
                user_aliases = json.load(f)
                result.update(user_aliases)
        except:
            pass

    return result


KNOWN_SLUGS = cldr_short_names(cldr_file=SCRIPT_CLDR_FILE, user_aliases_file=SCRIPT_USER_SHORTNAME_FILE)


def _show_matches(matches, buffer):
    weechat.prnt(buffer, "")

    longest_slug_len = max(len(slug) for slug, replacement in matches)
    term_width = int(weechat.info_get("term_width", ""))
    num_wide = min(3, term_width//(longest_slug_len+5))

    output = []
    for num, (slug, replacement) in enumerate(matches):
        field = f"{replacement}\t{slug}"
        output.append(f"{field:<{longest_slug_len+2}}")
        if num % num_wide == 0:
            weechat.prnt(buffer, "".join(output))
            output[:] = ()
    if output:
        weechat.prnt(buffer, "".join(output))

    weechat.prnt(buffer, "")


# TODO: this helper is kinda hard to read, clean up
def _extract_word(buffer) -> str:
    cursor_pos = weechat.buffer_get_integer(buffer, 'input_pos') - 1
    buf = weechat.buffer_get_string(buffer, 'input')

    if buf[cursor_pos] == " ":
        return ""

    left = buf[:cursor_pos].split()
    left = left[-1] if len(left) else ""

    right = buf[cursor_pos:].split()
    right = right[0] if len(right) else ""

    word = ''.join([left, right])

    return word


def completion_replacer(data, completion_item, buffer, completion):
    word = _extract_word(buffer)

    if not word.startswith(":"):
        return weechat.WEECHAT_RC_OK
    escaped = word.startswith("::")
    word = word.lstrip(":")

    def _is_close(word, slug):
        return slug.lstrip(":").startswith(word) or word in slug

    sw_matches = []
    other_matches = []
    for slug, replacement in KNOWN_SLUGS.items():
        if slug.lstrip(":").startswith(word):
            sw_matches.append((slug, replacement))
        elif word in slug:
            other_matches.append((slug, replacement))

    matches = sorted(chain(other_matches, sw_matches))

    if matches:
        for (slug, replacement) in matches:
            head = ":" if escaped else ""
            weechat.hook_completion_list_add(completion, head + slug, 0, weechat.WEECHAT_LIST_POS_SORT)

        _show_matches(matches, buffer)

    return weechat.WEECHAT_RC_OK


def modify_message(data, modifier, modifier_data, msg):
    idx = msg.index(':') + 1
    cmd, text = msg[:idx], msg[idx:]

    def _replace(match):
        if match:
            slug = match.group(0)
            return KNOWN_SLUGS.get(slug, slug)
        else:
            return None

    newmsg = cmd + re.sub(r":[\w-]+?:", _replace, text)

    return newmsg
