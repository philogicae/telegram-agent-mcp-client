import './globals.css'
import HeroUI from '@layout/HeroUI'
import Navbar from '@layout/Navbar'
import type { Metadata, Viewport } from 'next'
import { Roboto } from 'next/font/google'

const font = Roboto({
  subsets: ['latin'],
  weight: '400',
  preload: true,
})

const url = process.env.NEXT_PUBLIC_API_URL || 'https://rag-docs.rphi.xyz'

export const metadata: Metadata = {
  title: 'Docs UI',
  description: 'Docs UI for Telegram Agent',
  applicationName: 'Docs UI',
  appLinks: {
    web: {
      url: url,
      should_fallback: true,
    },
  },
  icons: {
    icon: '/favicon.ico',
    shortcut: '/favicon.ico',
    apple: '/apple-touch-icon.png',
  },
  manifest: '/manifest.json',
  metadataBase: new URL(url),
  openGraph: {
    title: 'Docs UI',
    description: 'Docs UI for Telegram Agent',
    url: url,
    siteName: 'Docs UI',
    images: [
      {
        url: `${url}/512x512.png`,
        width: 512,
        height: 512,
      },
    ],
    locale: 'en-US',
    type: 'website',
  },
  twitter: {
    card: 'summary',
    title: 'Docs UI',
    description: 'Docs UI for Telegram Agent',
    site: '@philogicae',
    creator: '@philogicae',
    images: [`${url}/512x512.png`],
  },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const csp = `default-src 'self' https://rag-api.rphi.xyz; style-src 'self' 'unsafe-inline' fonts.googleapis.com; font-src 'self' fonts.gstatic.com; img-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline'; object-src data:`
  return (
    <html lang="en" className={font.className}>
      <head>
        <meta httpEquiv="Content-Security-Policy" content={csp} />
      </head>
      <body>
        <HeroUI>
          <Navbar>{children}</Navbar>
        </HeroUI>
      </body>
    </html>
  )
}
