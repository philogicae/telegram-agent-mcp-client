import Image from 'next/image'

export default function Navbar({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col w-full h-full">
      <div className="absolute top-2 left-2 flex flex-row h-8 rounded-lg items-center justify-center bg-black ring-2 ring-black border-offset-1">
        <div className="flex border rounded-lg rounded-r-none overflow-hidden h-8 w-10 border-white">
          <Image src="/512x512.png" alt="Logo" width={64} height={64} />
        </div>
        <div className="flex h-8 w-full border border-l-0 rounded-lg rounded-l-none items-center justify-center border-white">
          <span className="text-2xl pl-1 pr-0.5 font-mono text-white">
            Docs UI
          </span>
        </div>
      </div>
      <div className="flex flex-col items-center justify-center w-full h-full">
        {children}
      </div>
    </div>
  )
}
