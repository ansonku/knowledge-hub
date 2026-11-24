/** Move focus and scroll to a rendered Markdown heading, optionally recording it in the address bar. */
export function jumpToHeading(article: HTMLElement | undefined, id: string, updateAddress = true) {
  const target = article?.querySelector<HTMLElement>(`[id="${id}"]`)
  if (!target) return
  target.focus({ preventScroll: true })
  target.scrollIntoView({ block: 'start' })
  if (updateAddress) history.replaceState(history.state, '', `#${id}`)
}
