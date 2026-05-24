/**
 * API Error Boundary Tests — Sprint 5
 */

import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import App from '../App'
import * as documentsApi from '../api/documents'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function clickElement(el) {
  act(() => { fireEvent.click(el) })
}

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../api/documents', () => ({
  fetchDocuments: vi.fn(),
  deleteDocument: vi.fn(),
  uploadDocument: vi.fn(),
}))

vi.mock('../components/PDFViewer/PDFViewer', () => ({
  default: ({ document }) =>
    document ? <div data-testid="pdf-viewer">PDF Viewer</div> : null,
}))

vi.mock('../components/UploadButton/UploadButton', () => ({
  default: ({ onUpload, onError }) => (
    <button
      data-testid="upload-btn"
      onClick={() => {
        documentsApi.uploadDocument(new File(['x'], 'test.pdf', { type: 'application/pdf' }))
          .then((doc) => onUpload?.(doc))
          .catch((err) => onError?.(err))
      }}
    >
      Upload
    </button>
  ),
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const DOCS = [
  {
    id: 'doc-001',
    filename: 'Report Q1.pdf',
    file_url: '/uploads/report-q1.pdf',
    size: 102400,
    uploaded_at: '2026-05-20T10:00:00Z',
  },
  {
    id: 'doc-002',
    filename: 'Handbook.pdf',
    file_url: '/uploads/handbook.pdf',
    size: 204800,
    uploaded_at: '2026-05-21T12:00:00Z',
  },
]

function makeAxiosError(status, detail) {
  const err = new Error(detail)
  err.response = { status, data: { detail } }
  return err
}

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  documentsApi.fetchDocuments.mockResolvedValue(DOCS)
  documentsApi.deleteDocument.mockResolvedValue({})
  documentsApi.uploadDocument.mockResolvedValue(DOCS[0])
})

afterEach(() => {
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// 1. Document list fetch errors
// ---------------------------------------------------------------------------

describe('API errors — document list fetch', () => {
  it('shows a user-friendly error message when fetch returns 500', async () => {
    documentsApi.fetchDocuments.mockRejectedValue(makeAxiosError(500, 'Internal Server Error'))
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    const alert = screen.getByRole('alert')
    expect(alert.textContent).not.toMatch(/500/)
    expect(alert.textContent.length).toBeGreaterThan(5)
  })

  it('shows a user-friendly error when fetch returns 503 (service unavailable)', async () => {
    documentsApi.fetchDocuments.mockRejectedValue(makeAxiosError(503, 'Service Unavailable'))
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('shows a network error message when fetch throws with no response (offline)', async () => {
    const networkErr = new Error('Network Error')
    documentsApi.fetchDocuments.mockRejectedValue(networkErr)
    render(<App />)

    await waitFor(() => {
      const alert = screen.getByRole('alert')
      expect(alert).toBeInTheDocument()
      expect(alert.textContent).toMatch(/network|connection|unavailable|try again/i)
    })
  })

  it('error alert is dismissible — hides after clicking dismiss', async () => {
    documentsApi.fetchDocuments.mockRejectedValue(makeAxiosError(500, 'Server error'))
    render(<App />)

    await waitFor(() => screen.getByRole('alert'))

    clickElement(screen.getByRole('button', { name: /dismiss|close|×/i }))

    await waitFor(() => {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })
  })

  it('provides a retry button that re-calls fetchDocuments', async () => {
    documentsApi.fetchDocuments
      .mockRejectedValueOnce(makeAxiosError(500, 'Server error'))
      .mockResolvedValueOnce(DOCS)

    render(<App />)

    await waitFor(() => screen.getByRole('alert'))

    clickElement(screen.getByRole('button', { name: /retry|try again/i }))

    await waitFor(() => {
      expect(documentsApi.fetchDocuments).toHaveBeenCalledTimes(2)
      expect(screen.getByText('Report Q1.pdf')).toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// 2. Delete errors
// ---------------------------------------------------------------------------

describe('API errors — document delete', () => {
  it('shows an error alert when delete returns 500', async () => {
    documentsApi.deleteDocument.mockRejectedValue(makeAxiosError(500, 'Delete failed'))
    render(<App />)

    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByRole('button', { name: /delete.*Report Q1/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('does NOT remove the document from the list when delete fails', async () => {
    documentsApi.deleteDocument.mockRejectedValue(makeAxiosError(500, 'Delete failed'))
    render(<App />)

    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByRole('button', { name: /delete.*Report Q1/i }))

    await waitFor(() => screen.getByRole('alert'))
    expect(screen.getByText('Report Q1.pdf')).toBeInTheDocument()
  })

  it('shows a user-friendly message for delete 404 (document not found)', async () => {
    documentsApi.deleteDocument.mockRejectedValue(makeAxiosError(404, 'Document not found'))
    render(<App />)

    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByRole('button', { name: /delete.*Report Q1/i }))

    await waitFor(() => {
      const alert = screen.getByRole('alert')
      expect(alert.textContent).toMatch(/not found|no longer exists|already deleted/i)
    })
  })

  it('delete error alert is dismissible', async () => {
    documentsApi.deleteDocument.mockRejectedValue(makeAxiosError(500, 'Delete failed'))
    render(<App />)

    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByRole('button', { name: /delete.*Report Q1/i }))

    await waitFor(() => screen.getByRole('alert'))

    clickElement(screen.getByRole('button', { name: /dismiss|close|×/i }))

    await waitFor(() => {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })
  })

  it('clears delete error when a subsequent delete succeeds', async () => {
    documentsApi.deleteDocument
      .mockRejectedValueOnce(makeAxiosError(500, 'Delete failed'))
      .mockResolvedValueOnce({})

    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    // First delete — fails
    clickElement(screen.getByRole('button', { name: /delete.*Report Q1/i }))
    await waitFor(() => screen.getByRole('alert'))

    // Dismiss error
    clickElement(screen.getByRole('button', { name: /dismiss|close|×/i }))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())

    // Second delete on Handbook — succeeds
    clickElement(screen.getByRole('button', { name: /delete.*Handbook/i }))
    await waitFor(() => {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(screen.queryByText('Handbook.pdf')).not.toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// 3. Upload errors surfaced through App
// ---------------------------------------------------------------------------

describe('API errors — upload propagation to App', () => {
  it('shows an error alert when upload fails with 413 (file too large)', async () => {
    documentsApi.uploadDocument.mockRejectedValue(
      makeAxiosError(413, 'File too large')
    )
    render(<App />)

    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByTestId('upload-btn'))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    const alert = screen.getByRole('alert')
    expect(alert.textContent).toMatch(/too large|size|50\s*MB/i)
  })

  it('shows an error alert when upload fails with 415 (unsupported media type)', async () => {
    documentsApi.uploadDocument.mockRejectedValue(
      makeAxiosError(415, 'Unsupported media type')
    )
    render(<App />)

    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByTestId('upload-btn'))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    const alert = screen.getByRole('alert')
    expect(alert.textContent).toMatch(/pdf|type|format/i)
  })

  it('shows generic error alert when upload fails with 500', async () => {
    documentsApi.uploadDocument.mockRejectedValue(
      makeAxiosError(500, 'Internal Server Error')
    )
    render(<App />)

    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByTestId('upload-btn'))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('does NOT add a new document to the list when upload fails', async () => {
    documentsApi.uploadDocument.mockRejectedValue(
      makeAxiosError(500, 'Internal Server Error')
    )
    render(<App />)

    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByTestId('upload-btn'))

    await waitFor(() => screen.getByRole('alert'))

    expect(screen.getAllByText('Report Q1.pdf')).toHaveLength(1)
    expect(screen.getAllByText('Handbook.pdf')).toHaveLength(1)
  })

  it('upload error is dismissible', async () => {
    documentsApi.uploadDocument.mockRejectedValue(
      makeAxiosError(500, 'Internal Server Error')
    )
    render(<App />)

    await waitFor(() => screen.getByText('Report Q1.pdf'))
    clickElement(screen.getByTestId('upload-btn'))

    await waitFor(() => screen.getByRole('alert'))

    clickElement(screen.getByRole('button', { name: /dismiss|close|×/i }))

    await waitFor(() => {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// 4. Multiple / simultaneous errors
// ---------------------------------------------------------------------------

describe('API errors — multiple error scenarios', () => {
  it('shows only one alert at a time — second error replaces first', async () => {
    documentsApi.fetchDocuments
      .mockRejectedValueOnce(makeAxiosError(500, 'Server error'))
      .mockResolvedValue(DOCS)

    render(<App />)

    await waitFor(() => screen.getByRole('alert'))

    expect(screen.getAllByRole('alert')).toHaveLength(1)
  })

  it('clearing error and then triggering another shows fresh alert', async () => {
    documentsApi.deleteDocument.mockRejectedValue(makeAxiosError(500, 'Delete failed'))
    render(<App />)

    await waitFor(() => screen.getByText('Report Q1.pdf'))

    // First error
    clickElement(screen.getByRole('button', { name: /delete.*Report Q1/i }))
    await waitFor(() => screen.getByRole('alert'))
    clickElement(screen.getByRole('button', { name: /dismiss|close|×/i }))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())

    // Second error
    clickElement(screen.getByRole('button', { name: /delete.*Handbook/i }))
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// 5. Accessibility of error messages
// ---------------------------------------------------------------------------

describe('API errors — accessibility', () => {
  it('error alert has role="alert" so screen readers announce it immediately', async () => {
    documentsApi.fetchDocuments.mockRejectedValue(makeAxiosError(500, 'Server error'))
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('dismiss/close button inside alert is keyboard focusable (not disabled)', async () => {
    documentsApi.fetchDocuments.mockRejectedValue(makeAxiosError(500, 'Server error'))
    render(<App />)

    await waitFor(() => screen.getByRole('alert'))

    const dismissBtn = screen.getByRole('button', { name: /dismiss|close|×/i })
    expect(dismissBtn).not.toBeDisabled()
  })

  it('error message is not empty — has meaningful text content', async () => {
    documentsApi.fetchDocuments.mockRejectedValue(makeAxiosError(500, 'Server error'))
    render(<App />)

    await waitFor(() => {
      const alert = screen.getByRole('alert')
      expect(alert.textContent.trim().length).toBeGreaterThan(10)
    })
  })
})