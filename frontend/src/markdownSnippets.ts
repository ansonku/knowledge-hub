// P11e: the syntax the editor offers in its help panel (Ctrl+/) and its slash menu (`/` at the start of a line).
// `insert` uses Monaco snippet syntax: ${1:placeholder} is selected after inserting, ${1|a,b|} offers choices,
// $0 is where the cursor ends up, and a literal $ is written \$.
export type Snippet = {
  id: string
  label: string
  /** Extra words the slash menu matches, e.g. English names. */
  keywords: string
  group: '文字' | '區塊' | '圖片與影片'
  description: string
  /** Snippet text, or an action the editor performs (opening its picture or video picker). */
  insert?: string
  action?: 'image' | 'video'
  /** What the help panel shows, when it differs from the inserted text. */
  example?: string
  /** Starts on its own line (block syntax); inline syntax goes in at the cursor. */
  block: boolean
}

export const SNIPPETS: Snippet[] = [
  { id: 'h2', label: '標題 2', keywords: 'heading h2 title', group: '文字', description: '段落標題', insert: '## ${1:標題}', block: true },
  { id: 'h3', label: '標題 3', keywords: 'heading h3 subtitle', group: '文字', description: '小節標題', insert: '### ${1:標題}', block: true },
  { id: 'bold', label: '粗體', keywords: 'bold strong', group: '文字', description: '強調文字（Ctrl+B）', insert: '**${1:文字}**', block: false },
  { id: 'link', label: '連結', keywords: 'link url', group: '文字', description: '文字連結（Ctrl+K）', insert: '[${1:文字}](${2:https://})', block: false },
  { id: 'quote', label: '引用', keywords: 'quote blockquote', group: '文字', description: '引用一段文字', insert: '> ${1:引用文字}', block: true },
  { id: 'bullet', label: '項目清單', keywords: 'list bullet ul', group: '文字', description: '按 Enter 接續下一項，Tab 縮排', insert: '- ${1:項目}', block: true },
  { id: 'ordered', label: '編號清單', keywords: 'list ordered number ol', group: '文字', description: '自動接續編號', insert: '1. ${1:項目}', block: true },
  { id: 'task', label: '待辦清單', keywords: 'task todo checkbox', group: '文字', description: '可勾選的項目', insert: '- [ ] ${1:待辦事項}', block: true },
  { id: 'rule', label: '分隔線', keywords: 'rule hr divider line', group: '文字', description: '水平分隔線', insert: '---\n$0', block: true },
  { id: 'code', label: '程式碼區塊', keywords: 'code fence pre', group: '區塊', description: '第一行寫語言名稱可上色，例如 bash、python', insert: '```${1:bash}\n${2:程式碼}\n```', block: true },
  { id: 'table', label: '表格', keywords: 'table grid', group: '區塊', description: '以 | 分欄，第二行是分隔線', insert: '| ${1:欄位 1} | 欄位 2 |\n| --- | --- |\n| 內容 | 內容 |', block: true },
  { id: 'mermaid', label: 'Mermaid 圖表', keywords: 'mermaid diagram flowchart chart', group: '區塊', description: '流程圖、時序圖等，閱讀時畫成圖', insert: '```mermaid\nflowchart LR\n  A[${1:開始}] --> B[${2:結束}]\n```', block: true },
  { id: 'math', label: '數學式', keywords: 'math katex latex formula', group: '區塊', description: 'LaTeX 數學式；行內寫 $x^2$', insert: '\\$\\$\n${1:E = mc^2}\n\\$\\$', block: true },
  { id: 'image', label: '圖片', keywords: 'image picture photo', group: '圖片與影片', description: '選擇圖片上傳；也可以直接貼上或拖入', action: 'image', example: '![圖片說明](/api/images/…/)', block: true },
  { id: 'video', label: '影片', keywords: 'video movie mp4 webm', group: '圖片與影片', description: 'MP4 或 WebM，200 MB 以內', action: 'video', example: '![影片說明](/api/videos/…/)', block: true },
  {
    id: 'gallery', label: '相簿', keywords: 'gallery album photos 照片 相片', group: '圖片與影片',
    description: '中間每行一張圖片；版面可選 justified、grid、masonry、vertical、carousel，不寫就用系統預設',
    insert: ':::gallery ${1|justified,grid,masonry,vertical,carousel|}\n$0\n:::',
    example: ':::gallery masonry\n![第 1 張](/api/images/…/)\n![第 2 張](/api/images/…/)\n:::', block: true,
  },
  { id: 'carousel', label: '輪播相簿', keywords: 'carousel slider slideshow gallery', group: '圖片與影片', description: '一次一張大圖，下方有縮圖列', insert: ':::gallery carousel\n$0\n:::', block: true },
]

export const SHORTCUTS: { keys: string; label: string }[] = [
  { keys: 'Ctrl+B', label: '粗體' },
  { keys: 'Ctrl+I', label: '斜體' },
  { keys: 'Ctrl+K', label: '連結' },
  { keys: 'Ctrl+S', label: '跳到「更新說明」，再按 Enter 儲存' },
  { keys: 'Ctrl+/', label: '開關這個語法說明' },
  { keys: 'Tab／Shift+Tab', label: '清單縮排／取消縮排' },
  { keys: '行首輸入 /', label: '快速插入（例如 /相簿、/表格、/影片）' },
  { keys: 'Ctrl+Z／Ctrl+Y', label: '復原／重做' },
]

/** Snippet text as the reader would type it: placeholders filled with their defaults. */
export function plainSnippet(snippet: Snippet) {
  if (snippet.example) return snippet.example
  return (snippet.insert ?? '')
    .replace(/\$\{\d+\|([^,|]*)[^}]*\|\}/g, '$1')
    .replace(/\$\{\d+:([^}]*)\}/g, '$1')
    .replace(/\$\d+/g, '')
    .replace(/\\\$/g, '$')
    .replace(/\n$/, '')
}
