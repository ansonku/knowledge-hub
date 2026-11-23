import mermaid from 'mermaid'

mermaid.initialize({
  startOnLoad: false,
  securityLevel: 'strict',
  htmlLabels: false,
  maxTextSize: 24_000,
  maxEdges: 250,
  suppressErrorRendering: true,
  secure: [
    'secure', 'securityLevel', 'startOnLoad', 'htmlLabels', 'maxTextSize',
    'maxEdges', 'suppressErrorRendering',
  ],
})

const drawing = document.getElementById('drawing')!
let sequence = 0

window.addEventListener('message', async event => {
  if (event.source !== window.parent || !event.origin || event.origin === 'null') return
  const data = event.data
  if (data?.type !== 'diagram-render' || typeof data.id !== 'string' || !Array.isArray(data.diagrams)) return
  const results: (string | null)[] = []
  for (const diagram of data.diagrams.slice(0, 20)) {
    try {
      if (typeof diagram !== 'string' || diagram.length > 24_000) throw new Error()
      const { svg } = await mermaid.render(`diagram-${++sequence}`, diagram, drawing)
      results.push(svg)
    } catch {
      results.push(null)
    } finally {
      drawing.replaceChildren()
    }
  }
  window.parent.postMessage({ type: 'diagram-result', id: data.id, results }, event.origin)
})
