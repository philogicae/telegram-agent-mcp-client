import { FiRefreshCw } from 'react-icons/fi'

export default function Generating() {
  return (
    <div className="h-full w-full flex flex-col items-center justify-center gap-3 bg-black text-white">
      <FiRefreshCw className="text-7xl animate-spin" />
      <span className="text-2xl">Generating Preview</span>
    </div>
  )
}
