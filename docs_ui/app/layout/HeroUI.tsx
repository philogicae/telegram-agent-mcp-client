'use client'
import { HeroUIProvider } from '@heroui/react'

export default function HeroUI({ children }: { children: React.ReactNode }) {
  return <HeroUIProvider className="w-full h-full">{children}</HeroUIProvider>
}
