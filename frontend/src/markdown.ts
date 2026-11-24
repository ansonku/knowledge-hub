import { katex } from '@mdit/plugin-katex'
import { tasklist } from '@mdit/plugin-tasklist'
import highlight from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import cpp from 'highlight.js/lib/languages/cpp'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import python from 'highlight.js/lib/languages/python'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'
import MarkdownIt from 'markdown-it'
import 'highlight.js/styles/github.css'
import 'katex/dist/katex.min.css'

type Heading = { id: string; text: string; level: number }
type RenderContext = { diagrams: string[] }
export type RenderedMarkdown = { html: string; headings: Heading[]; diagrams: string[] }

for (const [name, language] of Object.entries({ bash, cpp, javascript, json, python, sql, typescript, xml, yaml })) {
  highlight.registerLanguage(name, language)
}

const parser = new MarkdownIt({
  html: false,
  linkify: true,
  highlight(code, language) {
    if (code.length > 120_000 || !highlight.getLanguage(language)) return ''
    return `<pre><code class="hljs">${highlight.highlight(code, { language, ignoreIllegals: true }).value}</code></pre>`
  },
})
parser.use(tasklist)
parser.use(katex, { trust: false, throwOnError: false, maxExpand: 500, maxSize: 25 })

const image = parser.renderer.rules.image!
parser.renderer.rules.image = (tokens, index, options, context, renderer) => {
  tokens[index].attrSet('loading', 'lazy')
  tokens[index].attrSet('referrerpolicy', 'no-referrer')
  return image(tokens, index, options, context, renderer)
}

const fence = parser.renderer.rules.fence!
parser.renderer.rules.fence = (tokens, index, options, context, renderer) => {
  const token = tokens[index]
  if (token.info.trim().split(/\s+/)[0].toLowerCase() !== 'mermaid') {
    return fence(tokens, index, options, context, renderer)
  }
  const diagram = (context as RenderContext).diagrams.push(token.content) - 1
  return `<figure data-diagram="${diagram}"><pre><code>${parser.utils.escapeHtml(token.content)}</code></pre></figure>\n`
}

/** `sourceLines` marks each top-level block with its first source line (1-based), for the editor's synced preview. */
export function renderMarkdown(source: string, options: { sourceLines?: boolean } = {}): RenderedMarkdown {
  const context: RenderContext = { diagrams: [] }
  const headings: Heading[] = []
  const tokens = parser.parse(source, context)
  for (const [index, token] of tokens.entries()) {
    if (options.sourceLines && token.map && token.level === 0 && token.nesting >= 0) token.attrSet('data-source-line', String(token.map[0] + 1))
    if (token.type !== 'heading_open') continue
    const title = tokens[index + 1]
    const text = title.children?.map(part => part.children?.map(child => child.content).join('') ?? part.content).join('') || title.content
    const id = `section-${headings.length + 1}`
    token.attrSet('id', id)
    token.attrSet('tabindex', '-1')
    headings.push({ id, text, level: Number(token.tag.slice(1)) })
  }
  return { html: parser.renderer.render(tokens, parser.options, context), headings, diagrams: context.diagrams }
}
