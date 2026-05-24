import { useRef, useState } from 'react'
import { uploadDocument } from '../../api/documents'

const FIFTY_MB = 50 * 1024 * 1024

function validate(file) {
  const isPdfExtension = file.name.toLowerCase().endsWith('.pdf')
  const isPdfMime = file.type === 'application/pdf'

  if (!isPdfExtension || !isPdfMime) {
    return 'Only PDF files are supported. Please select a valid PDF.'
  }
  if (file.size > FIFTY_MB) {
    return 'File exceeds the 50 MB size limit. Please choose a smaller file.'
  }
  return null
}

export default function UploadButton({ onUpload, onError }) {
  const inputRef = useRef(null)
  const [localError, setLocalError] = useState(null)
  const [uploading, setUploading] = useState(false)

  async function handleChange(e) {
    const file = e.target.files?.[0]
    if (!file) return

    const validationError = validate(file)
    if (validationError) {
      setLocalError(validationError)
      return
    }

    setLocalError(null)
    setUploading(true)
    try {
      const doc = await uploadDocument(file)
      if (onUpload) onUpload(doc)
    } catch (err) {
      if (onError) {
        onError(err)
      } else {
        const detail = err?.response?.data?.detail
        setLocalError(detail ? detail : 'Upload failed. Please try again.')
      }
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  function handleButtonClick() {
    inputRef.current?.click()
  }

  function dismissError() {
    setLocalError(null)
  }

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,application/pdf"
        style={{ display: 'none' }}
        onChange={handleChange}
      />
      <button
        onClick={handleButtonClick}
        disabled={uploading || !!localError}
      >
        {uploading ? 'Uploading…' : 'Upload PDF'}
      </button>
      {localError && (
        <p role="alert" style={{ color: 'red', marginTop: '0.5rem', fontSize: '0.875rem' }}>
          {localError}
          {' '}
          <button
            type="button"
            onClick={dismissError}
            aria-label="Dismiss error"
            style={{ marginLeft: '0.5rem', background: 'none', border: 'none', color: 'red', cursor: 'pointer', padding: 0, fontSize: '0.875rem', textDecoration: 'underline' }}
          >
            Try again
          </button>
        </p>
      )}
    </div>
  )
}