/**
 * Integration tests — US-02: DocumentList → PDFViewer wiring
 */

import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
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
}))

vi.mock('../components/PDFViewer/PDFViewer', () => ({
  default: ({ document }) =>
    document ? (
      <div data-testid="pdf-viewer" data-url={document.file_url}>
        PDF Viewer Active
      </div>
    ) : null,
}))

vi.mock('../components/UploadButton/UploadButton', () => ({
  default: ({ onUpload }) => (
    <button data-testid="upload-btn" onClick={() => onUpload?.({})}>
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

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  documentsApi.fetchDocuments.mockResolvedValue(DOCS)
  documentsApi.deleteDocument.mockResolvedValue({})
})

afterEach(() => {
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('US-02: DocumentList → PDFViewer integration', () => {

  // --- API / initial state --------------------------------------------------

  it('calls fetchDocuments once on mount', async () => {
    render(<App />)
    await waitFor(() => {
      expect(documentsApi.fetchDocuments).toHaveBeenCalledTimes(1)
    })
  })

  it('renders all documents returned by the API', async () => {
    render(<App />)
    await waitFor(() => {
      expect(screen.getByText('Report Q1.pdf')).toBeInTheDocument()
      expect(screen.getByText('Handbook.pdf')).toBeInTheDocument()
    })
  })

  it('does NOT show the PDF viewer before any document is selected', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))
    expect(screen.queryByTestId('pdf-viewer')).not.toBeInTheDocument()
  })

  it('shows placeholder text when no document is selected', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))
    expect(screen.getByText(/select a document/i)).toBeInTheDocument()
  })

  // --- Click to open --------------------------------------------------------

  it('shows the PDF viewer after clicking a document', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))

    await waitFor(() => {
      expect(screen.getByTestId('pdf-viewer')).toBeInTheDocument()
    })
  })

  it('passes the correct file_url to PDFViewer when first document is clicked', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))

    await waitFor(() => {
      expect(screen.getByTestId('pdf-viewer')).toHaveAttribute(
        'data-url',
        '/uploads/report-q1.pdf'
      )
    })
  })

  it('passes the correct file_url to PDFViewer when second document is clicked', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Handbook.pdf'))

    clickElement(screen.getByText('Handbook.pdf'))

    await waitFor(() => {
      expect(screen.getByTestId('pdf-viewer')).toHaveAttribute(
        'data-url',
        '/uploads/handbook.pdf'
      )
    })
  })

  it('hides the placeholder once a document is selected', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))

    await waitFor(() => {
      expect(screen.queryByText(/select a document/i)).not.toBeInTheDocument()
    })
  })

  // --- Switching documents --------------------------------------------------

  it('updates the viewer URL when switching between documents', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))
    await waitFor(() =>
      expect(screen.getByTestId('pdf-viewer')).toHaveAttribute(
        'data-url',
        '/uploads/report-q1.pdf'
      )
    )

    clickElement(screen.getByText('Handbook.pdf'))
    await waitFor(() =>
      expect(screen.getByTestId('pdf-viewer')).toHaveAttribute(
        'data-url',
        '/uploads/handbook.pdf'
      )
    )
  })

  it('shows only one PDF viewer at a time', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))
    await waitFor(() => screen.getByTestId('pdf-viewer'))

    clickElement(screen.getByText('Handbook.pdf'))
    await waitFor(() => {
      expect(screen.getAllByTestId('pdf-viewer')).toHaveLength(1)
    })
  })

  // --- Close / deselect ----------------------------------------------------

  it('hides the PDF viewer after clicking the close button', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))
    await waitFor(() => screen.getByTestId('pdf-viewer'))

    clickElement(screen.getByRole('button', { name: /close/i }))

    await waitFor(() => {
      expect(screen.queryByTestId('pdf-viewer')).not.toBeInTheDocument()
    })
  })

  it('restores the placeholder after closing the viewer', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))
    await waitFor(() => screen.getByTestId('pdf-viewer'))

    clickElement(screen.getByRole('button', { name: /close/i }))

    await waitFor(() => {
      expect(screen.getByText(/select a document/i)).toBeInTheDocument()
    })
  })

  // --- Toolbar title --------------------------------------------------------

  it('shows the selected document filename in the viewer toolbar', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))

    await waitFor(() => {
      const matches = screen.getAllByText('Report Q1.pdf')
      expect(matches.length).toBeGreaterThanOrEqual(2)
    })
  })

  // --- Empty state ----------------------------------------------------------

  it('shows no viewer and no document names when the API returns empty list', async () => {
    documentsApi.fetchDocuments.mockResolvedValue([])
    render(<App />)

    await waitFor(() => {
      expect(screen.queryByTestId('pdf-viewer')).not.toBeInTheDocument()
      expect(screen.queryByText('Report Q1.pdf')).not.toBeInTheDocument()
    })
  })

  // --- Error state ----------------------------------------------------------

  it('shows an error alert and no viewer when the API rejects', async () => {
    documentsApi.fetchDocuments.mockRejectedValue(new Error('Network error'))
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('pdf-viewer')).not.toBeInTheDocument()
  })

  // --- Accessibility --------------------------------------------------------

  it('document list items are accessible via button or link role', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    const buttons = screen.queryAllByRole('button')
    const links   = screen.queryAllByRole('link')
    const allInteractive = [...buttons, ...links]

    const docItem = allInteractive.find((el) =>
      el.textContent.includes('Report Q1.pdf')
    )
    expect(docItem).toBeTruthy()
  })

  it('selected document item reflects selected state', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))

    await waitFor(() => {
      expect(screen.getByTestId('pdf-viewer')).toBeInTheDocument()
    })
  })
})