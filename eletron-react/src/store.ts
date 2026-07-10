import { create } from 'zustand'

// 全局 UI 状态
interface UIState {
  section: 'basic' | 'rent' | 'settings'
  sideBasic: 'buildings' | 'rooms' | 'tenants' | 'contracts' | 'water' | 'electric'
  sideRent: 'plan' | 'bills' | 'payments' | 'waterUsage' | 'electricUsage'
  planYear: number
  planMonth: number
  setSection: (s: UIState['section']) => void
  setSideBasic: (s: UIState['sideBasic']) => void
  setSideRent: (s: UIState['sideRent']) => void
  setPlanYearMonth: (year: number, month: number) => void
}

export const useUIStore = create<UIState>((set) => ({
  section: 'basic',
  sideBasic: 'buildings',
  sideRent: 'plan',
  planYear: new Date().getFullYear(),
  planMonth: new Date().getMonth() + 1,
  setSection: (s) => set({ section: s }),
  setSideBasic: (s) => set({ sideBasic: s }),
  setSideRent: (s) => set({ sideRent: s }),
  setPlanYearMonth: (year, month) => set({ planYear: year, planMonth: month }),
}))
