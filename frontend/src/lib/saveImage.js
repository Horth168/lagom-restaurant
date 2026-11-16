// Save a picture on any device:
// 1. Inside Telegram: Telegram's own download (the only way that works in the Mini App).
// 2. Phones (iPhone Safari, Android Chrome): the Share sheet, which offers "Save Image".
// 3. Computers: a normal file download.

function dataUrlToBlob(dataUrl) {
  const [head, body] = dataUrl.split(',')
  const type = head.match(/data:([^;]+)/)?.[1] || 'image/png'
  const bytes = atob(body)
  const out = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) out[i] = bytes.charCodeAt(i)
  return new Blob([out], { type })
}

/**
 * @param {{dataUrl: string, fileUrl?: string, fileName: string}} p
 *   dataUrl: the picture made in the page; fileUrl: the same picture as a real https file (for Telegram)
 * @returns {Promise<'telegram'|'shared'|'downloaded'|'cancelled'>}
 */
export async function saveImage({ dataUrl, fileUrl, fileName }) {
  const tg = window.Telegram?.WebApp
  if (fileUrl && tg?.initData && typeof tg.downloadFile === 'function' && tg.isVersionAtLeast?.('8.0')) {
    tg.downloadFile({ url: fileUrl, file_name: fileName })
    return 'telegram'
  }
  const blob = dataUrlToBlob(dataUrl)
  const file = new File([blob], fileName, { type: blob.type })
  const touch = window.matchMedia?.('(pointer: coarse)').matches
  if (touch && navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file] })
      return 'shared'
    } catch (e) {
      if (e?.name === 'AbortError') return 'cancelled'
      // sharing not allowed here: fall through to a download
    }
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 30000)
  return 'downloaded'
}
