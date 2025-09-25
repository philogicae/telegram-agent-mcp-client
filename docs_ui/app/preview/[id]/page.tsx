'use client'
import NotFound from '@components/NotFound'
import Previewing from '@components/Previewing'
import { CUSTOM_CSS } from '@utils/preview'
import DOMPurify from 'dompurify'
import { use, useCallback, useEffect, useState } from 'react'

export default function Preview({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const [htmlContent, setHtmlContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchPreview = useCallback(async (id: string) => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`/api/preview?id=${id}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch preview: ${response.statusText}`)
      }
      const html = await response.text()
      const sanitizedHtml = DOMPurify.sanitize(html, {
        FORBID_ATTR: ['style'],
      })
      const finalHtml = `<style>${CUSTOM_CSS}</style>${sanitizedHtml}`
      setHtmlContent(finalHtml)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!id) return
    fetchPreview(id)
  }, [id])

  if (loading) {
    return <Previewing />
  }
  if (error) {
    return <NotFound />
  }
  return (
    <div
      className="flex flex-col h-full w-full items-center justify-start p-8"
      /* biome-ignore lint/security/noDangerouslySetInnerHtml: The HTML is sanitized with DOMPurify */
      dangerouslySetInnerHTML={{ __html: htmlContent }}
    />
  )
}
