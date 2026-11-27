// P25: two-factor pages — six-box code input (fills a hidden field; paste and backspace work), the recovery-code
// switch on the sign-in page, copy and download buttons, and the "I have saved them" checkbox.
(function () {
  function otp(group) {
    var target = document.getElementById(group.dataset.target)
    var boxes = Array.prototype.slice.call(group.querySelectorAll('input'))
    var sync = function () { target.value = boxes.map(function (b) { return b.value }).join('') }
    boxes.forEach(function (box, i) {
      box.addEventListener('input', function () {
        box.value = box.value.replace(/\D/g, '').slice(-1); sync()
        if (box.value && boxes[i + 1]) boxes[i + 1].focus()
      })
      box.addEventListener('keydown', function (e) {
        if (e.key === 'Backspace' && !box.value && boxes[i - 1]) { boxes[i - 1].focus(); boxes[i - 1].value = ''; sync(); e.preventDefault() }
      })
      box.addEventListener('paste', function (e) {
        var text = ((e.clipboardData || window.clipboardData).getData('text') || '').replace(/\D/g, '')
        if (!text) return
        e.preventDefault()
        boxes.forEach(function (b, k) { b.value = text[k] || '' }); sync()
        ;(boxes[Math.min(text.length, boxes.length) - 1] || boxes[0]).focus()
      })
    })
    // Boxes replace the plain field only when this script runs.
    group.hidden = false
    var fallback = document.getElementById(group.dataset.fallback)
    if (fallback) fallback.hidden = true
    target.type = 'hidden'
  }
  document.querySelectorAll('.otp[data-target]').forEach(otp)

  // Sign-in: switch between the six boxes and a recovery code.
  document.querySelectorAll('[data-use-recovery]').forEach(function (button) {
    button.hidden = false
    button.addEventListener('click', function () {
      var form = button.closest('form'), boxes = form.querySelector('.otp'), field = form.querySelector('[data-recovery-field]')
      var target = document.getElementById(boxes.dataset.target)
      var recovery = !field.hidden
      field.hidden = recovery; boxes.hidden = !recovery
      target.type = 'hidden'; target.value = ''
      var input = field.querySelector('input')
      if (!recovery) { target.removeAttribute('name'); input.name = 'code'; input.focus(); button.textContent = button.dataset.back }
      else { input.removeAttribute('name'); target.name = 'code'; boxes.querySelector('input').focus(); button.textContent = button.dataset.label }
    })
  })

  document.querySelectorAll('[data-copy]').forEach(function (button) {
    button.addEventListener('click', function () {
      var text = button.dataset.copy || (document.getElementById(button.dataset.copyFrom) || {}).innerText || ''
      var done = function () { var label = button.textContent; button.textContent = '已複製'; setTimeout(function () { button.textContent = label }, 2000) }
      if (navigator.clipboard) navigator.clipboard.writeText(text.trim()).then(done, function () {})
    })
  })
  document.querySelectorAll('[data-download]').forEach(function (button) {
    button.addEventListener('click', function () {
      var text = (document.getElementById(button.dataset.download) || {}).innerText || ''
      var blob = new Blob([button.dataset.header + '\n\n' + text.trim() + '\n'], { type: 'text/plain;charset=utf-8' })
      var link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = button.dataset.filename
      document.body.appendChild(link); link.click(); link.remove(); setTimeout(function () { URL.revokeObjectURL(link.href) }, 1000)
    })
  })
  document.querySelectorAll('[data-enables]').forEach(function (box) {
    var target = document.getElementById(box.dataset.enables)
    var update = function () { target.classList.toggle('is-disabled', !box.checked); target.setAttribute('aria-disabled', String(!box.checked)) }
    target.addEventListener('click', function (e) { if (!box.checked) e.preventDefault() })
    box.addEventListener('change', update); update()
  })
})()
