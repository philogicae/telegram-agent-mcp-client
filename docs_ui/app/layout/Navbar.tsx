'use client'
import Image from 'next/image'
import { useCallback, useEffect, useState } from 'react'
import { FiMoon, FiSun } from 'react-icons/fi'

export default function Navbar({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'light')

  useEffect(() => {
    theme === 'dark' && document.documentElement.classList.add('dark')
  }, [])

  const toggleTheme = useCallback(() => {
    const newTheme = theme === 'light' ? 'dark' : 'light'
    setTheme(newTheme)
    localStorage.setItem('theme', newTheme)
    document.documentElement.classList.toggle('dark')
  }, [theme])

  return (
    <div className="flex flex-col w-full h-full bg-white dark:bg-black text-black dark:text-white">
      <div className="flex flex-col items-start justify-center w-full h-14 p-2">
        <div className="flex flex-row h-8 w-48 rounded-lg items-center justify-center bg-black ring-2 ring-black border-offset-1 gap-0.5">
          <div className="flex h-8 w-12 rounded-lg border dark:border-1.5 border-white ring-2 ring-black border-offset-1 bg-black text-white items-center justify-center rounded-r-none overflow-hidden">
            <Image src="/512x512.png" alt="Logo" width={64} height={64} />
          </div>
          <div className="flex h-8 w-36 border dark:border-1.5 border-white items-center justify-center">
            <span className="text-2xl pl-1 pr-0.5 font-mono text-white tracking-tighter">
              Docs UI
            </span>
          </div>
          <button
            type="button"
            onClick={toggleTheme}
            className="flex h-8 w-12 rounded-lg border dark:border-1.5 border-white ring-2 ring-black border-offset-1 bg-black text-white items-center justify-center rounded-l-none"
          >
            {theme === 'light' ? (
              <FiSun className="text-red-200" />
            ) : (
              <FiMoon className="text-cyan-200" />
            )}
          </button>
        </div>
      </div>
      <div className="flex flex-col items-center justify-center w-full h-full overflow-y-auto">
        {children}
      </div>
    </div>
  )
}
