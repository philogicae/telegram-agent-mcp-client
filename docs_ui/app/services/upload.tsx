'use client'

const upload = async (files: File[]): Promise<any> => {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/upload`, {
      method: 'POST',
      body: files as any,
    })
    if (res.ok) return await res.json()
    console.error('Request failed:', res.status)
  } catch (error) {
    console.error('Request error:', error)
  }
}

export default upload
