'use client'
import { FaArrowLeft, FaScrewdriverWrench } from 'react-icons/fa6'

export default function Maintenance() {
  return (
    <div className="flex flex-col items-center justify-center w-full h-full gap-6">
      <FaScrewdriverWrench className="text-6xl" />
      <span className="text-2xl font-bold">Maintenance</span>
      <a
        className={
          'w-20 h-8 text-lg text-white bg-gray-950 rounded-lg cursor-pointer hover:bg-gray-900 hover:shadow-lg flex items-center justify-center font-mono tracking-tighter font-semibold'
        }
        href="/"
      >
        <div className="text-sm flex flex-row items-center justify-center">
          <FaArrowLeft />
          <span className="pl-2">MENU</span>
        </div>
      </a>
    </div>
  )
}
