import './globals.css'
import HeroUI from '@layout/HeroUI'
import Navbar from '@layout/Navbar'
import { Roboto } from 'next/font/google'
import { Suspense } from 'react'
import Loading from './loading'

const font = Roboto({
  subsets: ['latin'],
  weight: '400',
  preload: true,
})

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={font.className}>
      <body>
        <HeroUI>
          <Suspense fallback={<Loading />}>
            <Navbar>{children}</Navbar>
          </Suspense>
        </HeroUI>
      </body>
    </html>
  )
}
