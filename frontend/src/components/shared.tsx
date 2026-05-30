import { useEffect, useState, type ReactNode } from 'react'

export function HelpTip({ text }: { text: string }) {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    function handleClick() { setOpen(false) }
    document.addEventListener('click', handleClick)
    return () => document.removeEventListener('click', handleClick)
  }, [open])

  return (
    <span className={`help-tip ${open ? 'is-open' : ''}`} onClick={(e) => e.stopPropagation()}>
      <button
        className="help-button"
        type="button"
        aria-label="查看填写说明"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        ?
      </button>
      {open ? <span className="help-popover">{text}</span> : null}
    </span>
  )
}

export function FormField(props: {
  label: string
  hint?: string
  helpText?: string
  spanTwo?: boolean
  children: ReactNode
}) {
  const { label, hint, helpText, spanTwo = false, children } = props
  const tipText = helpText ?? hint

  return (
    <div className={`field-block ${spanTwo ? 'span-two' : ''}`}>
      <span className="field-label-row">
        <span className="field-label">{label}</span>
        {tipText ? <HelpTip text={tipText} /> : null}
      </span>
      {children}
    </div>
  )
}

export function SectionHeader(props: {
  eyebrow: string
  title: string
  stateLabel?: string
  stateClass?: string
  collapsed?: boolean
  onToggle?: () => void
}) {
  const { eyebrow, title, stateLabel, stateClass, collapsed = false, onToggle } = props

  return (
    <header className="panel-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h3>{title}</h3>
      </div>
      <div className="panel-header-actions">
        {stateLabel ? <span className={`badge ${stateClass ?? ''}`}>{stateLabel}</span> : null}
        {onToggle ? (
          <button className="collapse-button" type="button" onClick={onToggle}>
            {collapsed ? '展开' : '收起'}
          </button>
        ) : null}
      </div>
    </header>
  )
}
