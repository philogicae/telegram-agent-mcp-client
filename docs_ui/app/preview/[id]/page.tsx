'use client'
import { use } from 'react'

export default function Preview({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  return <p>Preview: {id}</p>
}
