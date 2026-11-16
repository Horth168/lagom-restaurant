import { useState } from 'react'
import {
  CakeSlice, Citrus, Coffee, CupSoda, Fish, GlassWater, Popcorn, Sandwich, Soup, UtensilsCrossed, Wheat,
} from 'lucide-react'

// Shown until the owner uploads a real photo: a calm tile with a line icon, never fake food photography.
const ICONS = {
  coffee: Coffee, 'milk-tea': CupSoda, juice: Citrus, 'soft-drinks': GlassWater, desserts: CakeSlice,
  noodles: Soup, rice: Wheat, cambodian: Fish, chinese: Soup, western: Sandwich, snacks: Popcorn,
}

export function ProductImage({ src, alt, categorySlug, className = '', iconSize = 28 }) {
  const [failed, setFailed] = useState(false)
  if (src && !failed) {
    return (
      <img
        src={src}
        alt={alt}
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
        className={`object-cover bg-surface-2 ${className}`}
      />
    )
  }
  const Icon = ICONS[categorySlug] || UtensilsCrossed
  return (
    <div className={`flex items-center justify-center bg-surface-2 text-sand ${className}`} aria-hidden="true">
      <Icon size={iconSize} strokeWidth={1.25} />
    </div>
  )
}
