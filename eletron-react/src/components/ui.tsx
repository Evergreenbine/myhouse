import React, { useState, useEffect, useRef } from 'react'

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
  if (!el) {
    el = document.createElement('div')
    el.id = '_toast'
    el.className = 'toast'
    document.body.appendChild(el)
  }
  el.textContent = msg
  el.className = 'toast show'
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { el.className = 'toast' }, 2000)
}

export function ToastContainer() {
  return <div id="_toast" className="toast" />
}

// DatePicker 组件
export function DateField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="date-picker-wrap">
      <input type="date" className="soft-input" value={value} onChange={e => onChange(e.target.value)} />
    </div>
  )
}
