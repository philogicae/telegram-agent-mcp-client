import { type NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const id = searchParams.get('id')

  if (!id) {
    return NextResponse.json({ error: 'ID is required' }, { status: 400 })
  }

  try {
    const response = await fetch(`${process.env.RAG_URL}/preview/${id}`)
    if (!response.ok) {
      throw new Error(`Failed to fetch preview: ${response.statusText}`)
    }
    const html = await response.text()
    return new NextResponse(html, {
      headers: {
        'Content-Type': 'text/html',
      },
    })
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}
