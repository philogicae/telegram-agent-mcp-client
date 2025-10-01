'use client'
import NotFound from '@components/NotFound'
import Previewing from '@components/Previewing'
import { Button } from '@heroui/react'
import { CUSTOM_CSS } from '@utils/preview'
import DOMPurify from 'dompurify'
import { use, useCallback, useEffect, useRef, useState } from 'react'
import { FiDownload } from 'react-icons/fi'

export default function Preview({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const [htmlContent, setHtmlContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)

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

  const handleDownload = useCallback(async () => {
    if (!contentRef.current || downloading) return
    setDownloading(true)
    try {
      // Dynamically import html2pdf.js to avoid SSR issues
      const html2pdf = (await import('html2pdf.js')).default
      const element = contentRef.current
      const opt = {
        margin: 10,
        filename: `report-${id}.pdf`,
        image: { type: 'jpeg' as const, quality: 0.98 },
        html2canvas: { scale: 2, useCORS: true, logging: false },
        jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' as const },
        pagebreak: { mode: 'css', avoid: ['img', 'pre', 'table'] },
      }
      await html2pdf().set(opt).from(element).save()
    } catch (err: any) {
      console.error('Failed to generate PDF:', err)
    } finally {
      setDownloading(false)
    }
  }, [id, downloading, contentRef])

  if (loading) {
    return <Previewing />
  }
  if (error) {
    return <NotFound />
  }
  return (
    <>
      <div className="absolute top-2.5 right-2 flex flex-row h-8 w-32 items-center justify-center">
        <Button
          size="sm"
          onPress={handleDownload}
          disabled={downloading}
          className="inline-flex cursor-pointer rounded-lg text-white bg-black gap-2 text-md font-bold disabled:text-cyan-200 border border-black ring-2 ring-black border-offset-1 hover:text-cyan-200 items-center justify-center"
        >
          <FiDownload className="text-md" />
          <span className="text-xs font-mono tracking-tighter">
            {downloading ? 'Generating PDF...' : 'Export as PDF'}
          </span>
        </Button>
      </div>
      <div
        ref={contentRef}
        className="flex flex-col h-full w-full max-w-full items-center justify-start p-8 overflow-x-hidden break-words"
        /* biome-ignore lint/security/noDangerouslySetInnerHtml: The HTML is sanitized with DOMPurify */
        dangerouslySetInnerHTML={{ __html: htmlContent }}
      />
    </>
  )
}
