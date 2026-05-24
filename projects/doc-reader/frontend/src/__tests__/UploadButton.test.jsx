/**
 * TDD — US-05: Upload Validation Feedback
 *
 * RED phase: these tests define the desired behaviour.
 * Several will fail against the current implementation:
 *   - MIME-type check (only extension is checked today)
 *   - Button disabled while a validation error is active
 *   - onUpload prop name (App passes onUpload; component exposes onSuccess)
 */

import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import UploadButton from '../components/UploadButton/UploadButton'
import * as documentsApi from '../api/documents'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../api/documents', () => ({
  uploadDocument: vi.fn(),
}))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a synthetic File with controllable name, type, and size. */
function makeFile({ name = 'test.pdf', type = 'application/pdf', sizeBytes = 1024 } = {}) {
  const file = new File(['x'.repeat(Math.min(sizeBytes, 1))], name, { type })
  // File.size is read-only — override via Object.defineProperty
  Object.defineProperty(file, 'size', { value: sizeBytes })
  return file
}

/** Fire a change event on the hidden <input type="file"> inside the component.
 *  Uses async act() to flush all microtask/state-update queues. */
async function selectFile(inputEl, file) {
  Object.defineProperty(inputEl, 'files', { value: [file], configurable: true })
  await act(async () => {
    fireEvent.change(inputEl)
  })
}

function getFileInput(container) {
  return container.querySelector('input[type="file"]')
}

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  documentsApi.uploadDocument.mockResolvedValue({ id: 'new-doc', filename: 'test.pdf' })
})

afterEach(() => {
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('US-05: UploadButton — initial render', () => {
  it('renders the upload button', () => {
    const { container } = render(<UploadButton />)
    expect(screen.getByRole('button', { name: /upload pdf/i })).toBeInTheDocument()
  })

  it('renders no error message on initial load', () => {
    render(<UploadButton />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('button is enabled on initial render', () => {
    render(<UploadButton />)
    expect(screen.getByRole('button', { name: /upload pdf/i })).not.toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// File-type validation
// ---------------------------------------------------------------------------

describe('US-05: UploadButton — file type validation', () => {
  it('shows error when a .docx file is selected', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ name: 'report.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }))
    expect(screen.getByText(/only pdf files are supported/i)).toBeInTheDocument()
  })

  it('shows error when a .png file is selected', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ name: 'photo.png', type: 'image/png' }))
    expect(screen.getByText(/only pdf files are supported/i)).toBeInTheDocument()
  })

  it('shows error when file has .pdf extension but wrong MIME type', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ name: 'fake.pdf', type: 'text/plain' }))
    expect(screen.getByText(/only pdf files are supported/i)).toBeInTheDocument()
  })

  it('shows error when file has correct MIME type but wrong extension', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ name: 'document.txt', type: 'application/pdf' }))
    expect(screen.getByText(/only pdf files are supported/i)).toBeInTheDocument()
  })

  it('does NOT show error for a valid PDF (correct extension + MIME type)', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ name: 'valid.pdf', type: 'application/pdf' }))
    expect(screen.queryByText(/only pdf files are supported/i)).not.toBeInTheDocument()
  })

  it('does not call uploadDocument when file type is invalid', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ name: 'report.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }))
    expect(documentsApi.uploadDocument).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// Size validation
// ---------------------------------------------------------------------------

describe('US-05: UploadButton — size validation', () => {
  const FIFTY_MB = 50 * 1024 * 1024

  it('shows error when file exceeds 50 MB', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ sizeBytes: FIFTY_MB + 1 }))
    expect(screen.getByText(/50 mb/i)).toBeInTheDocument()
  })

  it('shows error text that mentions the limit clearly', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ sizeBytes: FIFTY_MB + 1 }))
    const msg = screen.getByText(/50 mb/i)
    expect(msg.textContent).toMatch(/exceed|limit|size/i)
  })

  it('does NOT show size error when file is exactly 50 MB', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ sizeBytes: FIFTY_MB }))
    expect(screen.queryByText(/50 mb/i)).not.toBeInTheDocument()
  })

  it('does NOT show size error when file is under 50 MB', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ sizeBytes: 1024 }))
    expect(screen.queryByText(/50 mb/i)).not.toBeInTheDocument()
  })

  it('does not call uploadDocument when file is too large', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ sizeBytes: FIFTY_MB + 1 }))
    expect(documentsApi.uploadDocument).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// Error display & accessibility
// ---------------------------------------------------------------------------

describe('US-05: UploadButton — error message presentation', () => {
  it('error message is visible in the DOM (not hidden)', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ name: 'bad.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }))
    const err = screen.getByText(/only pdf files are supported/i)
    expect(err).toBeVisible()
  })

  it('error message has role="alert" for screen-reader accessibility', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ name: 'bad.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }))
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('error message is inline (not a modal or dialog)', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ name: 'bad.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByText(/only pdf files are supported/i)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Button disabled state during error
// ---------------------------------------------------------------------------

describe('US-05: UploadButton — button state', () => {
  it('upload button is disabled when a validation error is active', async () => {
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile({ name: 'bad.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }))
    expect(screen.getByRole('button', { name: /upload pdf/i })).toBeDisabled()
  })

  it('upload button re-enables after a valid file replaces the invalid one', async () => {
    const { container } = render(<UploadButton />)
    const input = getFileInput(container)

    // Select invalid file → error + disabled
    await selectFile(input, makeFile({ name: 'bad.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }))
    expect(screen.getByRole('button', { name: /upload pdf/i })).toBeDisabled()

    // Select valid file → error clears → button enabled
    await selectFile(input, makeFile({ name: 'good.pdf', type: 'application/pdf' }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /upload pdf/i })).not.toBeDisabled()
    })
  })
})

// ---------------------------------------------------------------------------
// Error auto-clear
// ---------------------------------------------------------------------------

describe('US-05: UploadButton — error auto-clears on valid selection', () => {
  it('clears file-type error when user subsequently selects a valid PDF', async () => {
    const { container } = render(<UploadButton />)
    const input = getFileInput(container)

    await selectFile(input, makeFile({ name: 'bad.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }))
    expect(screen.getByText(/only pdf files are supported/i)).toBeInTheDocument()

    await selectFile(input, makeFile({ name: 'good.pdf', type: 'application/pdf' }))
    expect(screen.queryByText(/only pdf files are supported/i)).not.toBeInTheDocument()
  })

  it('clears size error when user subsequently selects a valid smaller PDF', async () => {
    const FIFTY_MB = 50 * 1024 * 1024
    const { container } = render(<UploadButton />)
    const input = getFileInput(container)

    await selectFile(input, makeFile({ sizeBytes: FIFTY_MB + 1 }))
    expect(screen.getByText(/50 mb/i)).toBeInTheDocument()

    await selectFile(input, makeFile({ sizeBytes: 1024 }))
    expect(screen.queryByText(/50 mb/i)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// onUpload prop (App.jsx passes onUpload; component currently exposes onSuccess)
// ---------------------------------------------------------------------------

describe('US-05: UploadButton — onUpload prop contract', () => {
  it('calls onUpload callback after a successful upload', async () => {
    const onUpload = vi.fn()
    const { container } = render(<UploadButton onUpload={onUpload} />)
    await selectFile(getFileInput(container), makeFile())
    await waitFor(() => {
      expect(onUpload).toHaveBeenCalledTimes(1)
    })
  })

  it('passes the new document object to onUpload', async () => {
    const onUpload = vi.fn()
    const returnedDoc = { id: 'new-doc', filename: 'test.pdf' }
    documentsApi.uploadDocument.mockResolvedValue(returnedDoc)

    const { container } = render(<UploadButton onUpload={onUpload} />)
    await selectFile(getFileInput(container), makeFile())
    await waitFor(() => {
      expect(onUpload).toHaveBeenCalledWith(returnedDoc)
    })
  })
})

// ---------------------------------------------------------------------------
// Upload error from API
// ---------------------------------------------------------------------------

describe('US-05: UploadButton — API error handling', () => {
  it('shows upload-failed error message when API rejects', async () => {
    documentsApi.uploadDocument.mockRejectedValue(new Error('Server error'))
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile())
    await waitFor(() => {
      expect(screen.getByText(/upload failed/i)).toBeInTheDocument()
    })
  })

  it('shows server detail message when API returns a detail field', async () => {
    documentsApi.uploadDocument.mockRejectedValue({ response: { data: { detail: 'Duplicate file.' } } })
    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile())
    await waitFor(() => {
      expect(screen.getByText(/duplicate file/i)).toBeInTheDocument()
    })
  })

  it('shows uploading state while upload is in progress', async () => {
    let resolveUpload
    documentsApi.uploadDocument.mockReturnValue(new Promise((res) => { resolveUpload = res }))

    const { container } = render(<UploadButton />)
    await selectFile(getFileInput(container), makeFile())

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /uploading/i })).toBeInTheDocument()
    })

    await act(async () => {
      resolveUpload({ id: 'done' })
    })
  })
})