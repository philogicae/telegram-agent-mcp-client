'use client'
import Landing from '@components/frames/Landing'
import Loading from '@components/frames/Loading'
import Maintenance from '@components/frames/Maintenance'
import NotFound from '@components/frames/NotFound'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo } from 'react'
import { createHashRouter, redirect } from 'react-router'
import { RouterProvider } from 'react-router/dom'

const hydrateFallbackElement = <Loading />

export default function Home() {
  const router = useRouter()
  const isReady = typeof window !== 'undefined'
  const hashRouter = useMemo(
    () =>
      isReady
        ? createHashRouter([
            {
              path: '',
              element: <Landing />,
              hydrateFallbackElement,
            },
            {
              path: 'down',
              element: <Maintenance />,
              hydrateFallbackElement,
            },
            { path: '404', element: <NotFound />, hydrateFallbackElement },
            {
              path: '*',
              loader: async () => redirect('404'),
              hydrateFallbackElement,
            },
          ])
        : null,
    [isReady]
  )

  useEffect(() => {
    if (isReady && window.location.pathname + window.location.hash === '/')
      router.replace('/#/')
  }, [isReady])

  return hashRouter ? (
    <RouterProvider router={hashRouter} />
  ) : (
    hydrateFallbackElement
  )
}
