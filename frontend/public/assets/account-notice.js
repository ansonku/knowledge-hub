// Announcement banner on the Django account pages (P6c): hide it once dismissed in this browser.
// Same storage key as frontend/src/site/SiteNotice.vue; editing the announcement gives it a new id.
(function () {
  var KEY = 'knowledge-hub.notice-dismissed'
  var banner = document.querySelector('.notice[data-notice-id]')
  if (!banner) return
  var id = banner.getAttribute('data-notice-id')
  var dismissed = null
  try { dismissed = localStorage.getItem(KEY) } catch (error) { /* storage disabled: always show */ }
  if (dismissed === id) { banner.remove(); return }
  var close = banner.querySelector('.notice-close')
  close.hidden = false
  close.addEventListener('click', function () {
    try { localStorage.setItem(KEY, id) } catch (error) { /* hidden for this page only */ }
    banner.remove()
  })
})()
