import React, { useState, useEffect, useRef } from 'react'

import { DatePicker as AntDatePicker } from 'antd'
import dayjs from 'dayjs'

// Modal 弹窗
export function Modal({ open, onClose, title, children }: {
  open: boolean; onClose: () => void; title?: string; children: React.ReactNode
}) {
  if (!open) return null
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        {title && <div className="modal-title">{title}</div>}
        {children}
      </div>
    </div>
  )
}

// 自定义下拉选择
export function Select({ value, onChange, options, placeholder }: {
  value: string | number
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const selected = options.find(o => String(o.value) === String(value))

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={ref} className="custom-select" style={{position:'relative'}}>
      <div
        className="soft-input"
        style={{display:'flex',alignItems:'center',justifyContent:'space-between',cursor:'pointer',paddingRight:8}}
        onClick={() => setOpen(!open)}
      >
        <span style={selected ? {} : {color:'var(--text-third)'}}>
          {selected?.label || placeholder || '请选择'}
        </span>
        <span style={{fontSize:10,color:'var(--text-third)'}}>▼</span>
      </div>
      {open && (
        <div className="select-menu" style={{display:'block',position:'absolute',left:0,right:0,top:'100%',marginTop:4,background:'var(--white)',border:'1px solid var(--border-light)',borderRadius:8,boxShadow:'var(--shadow-md)',padding:6,zIndex:50,maxHeight:200,overflow:'auto'}}>
          {options.map(o => (
            <div
              key={o.value}
              className={'select-option' + (String(value) === String(o.value) ? ' active' : '')}
              onClick={() => { onChange(o.value); setOpen(false) }}
            >{o.label}</div>
          ))}
        </div>
      )}
    </div>
  )
}

// 按钮
export function Button({ children, type, size, onClick, className, ...rest }: {
  children: React.ReactNode
  type?: 'primary' | 'outline' | 'danger' | 'success'
  size?: 'sm'
  onClick?: () => void
  className?: string
  [key: string]: any
}) {
  var cls = 'btn'
  if (type === 'primary') cls += ' btn-primary'
  else if (type === 'danger') cls += ' btn-danger'
  else if (type === 'success') cls += ' btn-success'
  else cls += ' btn-outline'
  if (size === 'sm') cls += ' btn-sm'
  if (className) cls += ' ' + className
  return <button className={cls} onClick={onClick} {...rest}>{children}</button>
}

// 输入框
export function Input({ value, onChange, placeholder, type, className, ...rest }: {
  value?: string | number
  onChange?: (v: string) => void
  placeholder?: string
  type?: string
  className?: string
  [key: string]: any
}) {
  var cls = 'soft-input'
  if (className) cls += ' ' + className
  return (
    <input
      type={type || 'text'}
      value={value ?? ''}
      onChange={e => onChange?.(e.target.value)}
      placeholder={placeholder}
      className={cls}
      {...rest}
    />
  )
}

// Toast
let toastTimer: any = null
export function showToast(msg: string) {
  var el = document.getElementById('_toast')
  if (!el) {
    el = document.createElement('div')
    el.id = '_toast'
    el.className = 'toast'
    document.body.appendChild(el)
  }
  const toastEl = el
  toastEl.textContent = msg
  toastEl.className = 'toast show'
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastEl.className = 'toast' }, 2000)
}

export function ToastContainer() {
  return <div id="_toast" className="toast" />
}

// 统一使用 Ant Design 月份面板，保证 Electron 和浏览器中的交互一致
export function MonthPicker({ value, onChange, ariaLabel, style }: {
  value: string
  onChange: (v: string) => void
  ariaLabel?: string
  style?: React.CSSProperties
}) {
  const selected = /^\d{4}-\d{2}$/.test(value || '') ? dayjs(value + '-01') : null

  return (
    <div className="month-picker-wrap" style={style}>
      <AntDatePicker
        className="app-month-picker"
        picker="month"
        value={selected}
        format="YYYY年M月"
        allowClear
        inputReadOnly
        suffixIcon={null}
        aria-label={ariaLabel || '选择月份'}
        onChange={date => onChange(date ? date.format('YYYY-MM') : '')}
      />
    </div>
  )
}

// 统一使用 Ant Design 日期面板，值仍按后端需要的 YYYY-MM-DD 格式传递
export function DayPicker({ value, onChange, ariaLabel, style }: {
  value: string
  onChange: (v: string) => void
  ariaLabel?: string
  style?: React.CSSProperties
}) {
  const selected = /^\d{4}-\d{2}-\d{2}$/.test(value || '') ? dayjs(value) : null

  return (
    <AntDatePicker
      className="app-day-picker"
      value={selected}
      format="YYYY年M月D日"
      allowClear
      inputReadOnly
      suffixIcon={null}
      style={style}
      aria-label={ariaLabel || '选择日期'}
      onChange={date => onChange(date ? date.format('YYYY-MM-DD') : '')}
    />
  )
}

// DatePicker 组件
﻿export function DatePicker({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const [open, setOpen] = useState(false)
  const [viewYear, setViewYear] = useState(new Date().getFullYear())
  const [viewMonth, setViewMonth] = useState(new Date().getMonth() + 1)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  useEffect(() => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return
    const selectedDate = dayjs(value)
    if (selectedDate.isValid()) {
      setViewYear(selectedDate.year())
      setViewMonth(selectedDate.month() + 1)
    }
  }, [value, onChange])

  const daysInMonth = (y: number, m: number) => new Date(y, m, 0).getDate()
  const firstDayOfWeek = (y: number, m: number) => new Date(y, m - 1, 1).getDay()

  const today = new Date()
  const todayStr = today.getFullYear() + "-" + String(today.getMonth() + 1).padStart(2, "0") + "-" + String(today.getDate()).padStart(2, "0")

  const handlePrevMonth = () => {
    if (viewMonth === 1) { setViewMonth(12); setViewYear(viewYear - 1) }
    else setViewMonth(viewMonth - 1)
  }
  const handleNextMonth = () => {
    if (viewMonth === 12) { setViewMonth(1); setViewYear(viewYear + 1) }
    else setViewMonth(viewMonth + 1)
  }

  const handleSelect = (day: number) => {
    const ds = viewYear + "-" + String(viewMonth).padStart(2, "0") + "-" + String(day).padStart(2, "0")
    onChange(ds)
    setOpen(false)
  }

  const displayValue = value || ""
  const weeks = [
    "\u4e00", "\u4e8c", "\u4e09", "\u56db", "\u4e94", "\u516d", "\u65e5"
  ]
  const days = daysInMonth(viewYear, viewMonth)
  const fwd = firstDayOfWeek(viewYear, viewMonth)
  const blanks = fwd === 0 ? 6 : fwd - 1

  return (
    <div ref={ref} className="date-picker-wrap" style={{position:"relative"}}>
      <div className="date-picker-input" onClick={() => setOpen(!open)}>
        <span className="date-picker-text" style={displayValue ? {} : {color:"var(--text-third)"}}>
          {displayValue || placeholder || "\u8bf7\u9009\u62e9\u65e5\u671f"}
        </span>
        {displayValue && (
          <button
            type="button"
            aria-label="清空日期"
            onClick={e => { e.stopPropagation(); onChange(''); setOpen(false) }}
            style={{position:'absolute',right:28,top:'50%',transform:'translateY(-50%)',border:'none',background:'transparent',color:'var(--text-third)',cursor:'pointer',fontSize:16,lineHeight:1,padding:0,width:16,height:16}}
          >×</button>
        )}
        <span className="date-picker-icon">{String.fromCodePoint(0x1F4C5)}</span>
      </div>
      {open && (
        <div className="date-picker-dropdown" style={{display:"block"}}>
          <div className="dp-header">
            <span className="dp-nav" onClick={handlePrevMonth}>{String.fromCodePoint(0x25C0)}</span>
            <span className="dp-title">{viewYear}年{viewMonth}月</span>
            <span className="dp-nav" onClick={handleNextMonth}>{String.fromCodePoint(0x25B6)}</span>
          </div>
          <div className="dp-week-row">
            {weeks.map(w => <span key={w}>{w}</span>)}
          </div>
          <div className="dp-day-grid">
            {Array.from({length:blanks},(_,i) => <div key={"b"+i} className="dp-day-cell" />)}
            {Array.from({length:days},(_,i) => {
              const day = i + 1
              const ds = viewYear + "-" + String(viewMonth).padStart(2,"0") + "-" + String(day).padStart(2,"0")
              let cls = "dp-day-cell"
              if (ds === value) cls += " active"
              if (ds === todayStr) cls += " today"
              return <div key={day} className={cls} onClick={() => handleSelect(day)}>{day}</div>
            })}
          </div>
        </div>
      )}
    </div>
  )
}

