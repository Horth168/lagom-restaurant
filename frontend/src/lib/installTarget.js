// "Add to Home Screen" opens the app's start address, not the page you were on.
// On staff pages we point the phone at the staff install profile, so the home-screen
// icon opens the dashboard (sign-in first if needed; cashiers go on to the POS and
// kitchen staff to the kitchen screen). Everywhere else customers get the menu app.
import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

const STAFF = /^\/(admin|pos|kds|login)(\/|$)/

function setHead(staff) {
  const link = document.querySelector('link[rel="manifest"]')
  if (link) {
    if (!link.dataset.customer) link.dataset.customer = link.getAttribute('href')
    link.setAttribute('href', staff ? '/manifest-staff.webmanifest' : link.dataset.customer)
  }
  const title = document.querySelector('meta[name="apple-mobile-web-app-title"]')
  if (title) title.setAttribute('content', staff ? 'LAGOM Staff' : 'LAGOM')
}

export function useInstallTarget() {
  const { pathname } = useLocation()
  useEffect(() => setHead(STAFF.test(pathname)), [pathname])
}
