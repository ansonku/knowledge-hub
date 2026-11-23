import re
from html.parser import HTMLParser

import nh3
import tinycss2

HTML_TAGS = set(
    "a abbr article b blockquote br caption code dd del div dl dt em figcaption figure "
    "h1 h2 h3 h4 h5 h6 hr i kbd li main mark ol p pre s samp section small span "
    "strong sub sup table tbody td th thead tfoot tr u ul".split()
)
SVG_TAGS = set(
    "svg g defs desc path rect circle ellipse line polyline polygon text tspan marker "
    "linearGradient radialGradient stop clipPath mask use".split()
)
SVG_ATTRIBUTES = set(
    "id class role aria-label aria-labelledby aria-describedby viewBox preserveAspectRatio "
    "x y x1 y1 x2 y2 dx dy cx cy fx fy r rx ry width height d points transform "
    "textLength lengthAdjust text-anchor dominant-baseline alignment-baseline refX refY markerWidth markerHeight markerUnits orient "
    "gradientUnits gradientTransform offset clipPathUnits maskUnits maskContentUnits".split()
)
PAINT_PROPERTIES = set(
    "fill fill-opacity fill-rule stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin "
    "stroke-dasharray stroke-dashoffset stroke-miterlimit opacity stop-color stop-opacity "
    "clip-path clip-rule mask marker-start marker-mid marker-end".split()
)
CSS_PROPERTIES = PAINT_PROPERTIES | set(
    "font font-family font-size font-weight font-style text-anchor dominant-baseline "
    "alignment-baseline letter-spacing min-width max-width width min-height max-height height "
    "display color background background-color border border-top border-right border-bottom border-left "
    "border-color border-width border-style border-radius border-collapse box-sizing "
    "padding padding-block padding-inline padding-top padding-right padding-bottom padding-left "
    "margin margin-block margin-inline margin-top margin-right margin-bottom margin-left "
    "grid-template-columns grid-template-rows grid-column grid-row grid-auto-flow "
    "gap column-gap row-gap flex flex-direction flex-wrap align-items justify-content "
    "text-align white-space line-height overflow overflow-x overflow-y".split()
)
ATTRIBUTES = {tag: SVG_ATTRIBUTES | PAINT_PROPERTIES | {"style"} for tag in SVG_TAGS}
ATTRIBUTES.update({
    "*": {"id", "class", "role", "aria-label", "aria-labelledby", "aria-describedby", "title", "style"},
    "a": {"href"}, "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan", "scope"},
    "use": ATTRIBUTES["use"] | {"href"},
})
SELECTOR = re.compile(r"[\w.#>+~\s-]+")
FRAGMENT = re.compile(r"#[\w:.-]+")


CSS_FUNCTIONS = {"var", "repeat", "minmax", "calc", "min", "max", "clamp", "rgb", "rgba", "hsl", "hsla"}


def safe_tokens(tokens, depth=0):
    if depth > 16:
        return False
    for token in tokens:
        if token.type == "url":
            if not FRAGMENT.fullmatch(token.value):
                return False
        elif token.type == "function":
            if token.lower_name == "url":
                args = [item for item in token.arguments if item.type != "whitespace"]
                if len(args) != 1 or args[0].type != "string" or not FRAGMENT.fullmatch(args[0].value):
                    return False
            elif token.lower_name not in CSS_FUNCTIONS or not safe_tokens(token.arguments, depth + 1):
                return False
        elif token.type not in {"whitespace", "ident", "number", "dimension", "percentage", "hash", "string", "literal"}:
            return False
    return True


def clean_declarations(source, *, variables=False):
    declarations = []
    for item in tinycss2.parse_declaration_list(source, skip_comments=True, skip_whitespace=True):
        if item.type != "declaration":
            continue
        allowed = item.name.startswith("--") if variables else item.lower_name in CSS_PROPERTIES
        if allowed and safe_tokens(item.value):
            declarations.append(item)
    return tinycss2.serialize(declarations)


class StyleBlocks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside_style = False
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        if tag == "style":
            self.inside_style = True

    def handle_endtag(self, tag):
        if tag == "style":
            self.inside_style = False

    def handle_data(self, data):
        if self.inside_style:
            self.blocks.append(data)


def reading_styles(body):
    parser = StyleBlocks()
    parser.feed(body)
    parser.close()
    rules = []
    for block in parser.blocks:
        for rule in tinycss2.parse_stylesheet(block, skip_whitespace=True, skip_comments=True):
            if rule.type != "qualified-rule":
                continue
            selector = tinycss2.serialize(rule.prelude).strip()
            if selector == ":root":
                declarations = clean_declarations(rule.content, variables=True)
            elif all(SELECTOR.fullmatch(part.strip()) for part in selector.split(",")):
                declarations = clean_declarations(rule.content)
                selector = f":is({selector}):is(.public-html-body *)"
            else:
                continue
            if declarations:
                rules.append(f"{selector}{{{declarations}}}")
    return "\n".join(rules).replace("<", r"\3c ")


def clean_attribute(tag, attr, value):
    if attr == "style":
        return clean_declarations(value) or None
    if tag in SVG_TAGS:
        if attr == "href" and not FRAGMENT.fullmatch(value):
            return None
        if attr in PAINT_PROPERTIES and not safe_tokens(tinycss2.parse_component_value_list(value)):
            return None
    return value


def readable_html(body):
    cleaned = nh3.clean(
        body,
        tags=HTML_TAGS | SVG_TAGS,
        attributes=ATTRIBUTES,
        attribute_filter=clean_attribute,
        clean_content_tags={"script", "style", "iframe", "object", "math", "template", "head", "title", "foreignObject"},
        url_schemes={"http", "https", "mailto"},
    )
    if styles := reading_styles(body):
        return f"<style>{styles}</style>\n{cleaned}"
    return cleaned
