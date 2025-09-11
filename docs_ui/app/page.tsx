import { FaBan } from 'react-icons/fa6'

export default function Home() {
  return (
    <div className="h-40 w-40 flex flex-col items-center justify-center gap-3 bg-black text-white rounded-lg">
      <FaBan className="text-7xl" />
      <span className="text-2xl font-bold">Restricted</span>
    </div>
  )
}
