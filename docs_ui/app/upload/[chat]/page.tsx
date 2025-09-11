'use client'
import { use } from 'react'

export default function Upload({
  params,
}: {
  params: Promise<{ chat: string }>
}) {
  const { chat } = use(params)
  return <p>Upload: {chat}</p>
}
