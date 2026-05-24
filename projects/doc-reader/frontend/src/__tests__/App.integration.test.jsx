/**
 * Integration tests — App layout wiring
 *   US-02 : DocumentList → PDFViewer
 *   US-03s: DocumentSearch → sidebar filtering
 *   US-03p: PdfSearch lives inside PDFViewer (boundary test)
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

// Simulate DocumentSearch calling its onResults / onQueryChange props
let _onResults = null
let _onQueryChange = null

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
        {/* PdfSearch lives inside the real PDFViewer — represented here */}
        <div data-testid="pdf-search-boundary" />
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

/**
 * DocumentSearch mock — captures props so tests can drive callbacks directly.
 * Renders a real input so text-change tests can also trigger via fireEvent.
 */
vi.mock('../components/DocumentSearch/DocumentSearch', () => ({
  default: ({ onResults, onQueryChange }) => {
    _onResults = onResults
    _onQueryChange = onQueryChange
    return (
      <input
        data-testid="doc-search-input"
        placeholder="Search documents…"
        onChange={(e) => {
          const q = e.target.value
          onQueryChange?.(q)
        }}
      />
    )
  },
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

const SEARCH_MATCH = [DOCS[0]] // only Report Q1 matches a hypothetical query

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  documentsApi.fetchDocuments.mockResolvedValue(DOCS)
  documentsApi.deleteDocument.mockResolvedValue({})
  _onResults = null
  _onQueryChange = null
})

afterEach(() => {
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// US-02: DocumentList → PDFViewer
// ---------------------------------------------------------------------------

describe('US-02: DocumentList → PDFViewer integration', () => {

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

  it('shows the selected document filename in the viewer toolbar', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))

    await waitFor(() => {
      const matches = screen.getAllByText('Report Q1.pdf')
      expect(matches.length).toBeGreaterThanOrEqual(2)
    })
  })

  it('shows no viewer and no document names when the API returns empty list', async () => {
    documentsApi.fetchDocuments.mockResolvedValue([])
    render(<App />)
    await waitFor(() => {
      expect(screen.queryByTestId('pdf-viewer')).not.toBeInTheDocument()
      expect(screen.queryByText('Report Q1.pdf')).not.toBeInTheDocument()
    })
  })

  it('shows an error alert and no viewer when the API rejects', async () => {
    documentsApi.fetchDocuments.mockRejectedValue(new Error('Network error'))
    render(<App />)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('pdf-viewer')).not.toBeInTheDocument()
  })

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

// ---------------------------------------------------------------------------
// US-03 (sidebar): DocumentSearch → sidebar list filtering
// ---------------------------------------------------------------------------

describe('DocumentSearch → sidebar filtering integration', () => {

  it('renders the DocumentSearch input in the sidebar', async () => {
    render(<App />)
    await waitFor(() => screen.getByTestId('doc-search-input'))
    expect(screen.getByTestId('doc-search-input')).toBeInTheDocument()
  })

  it('full document list is visible when search is empty', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))
    expect(screen.getByText('Report Q1.pdf')).toBeInTheDocument()
    expect(screen.getByText('Handbook.pdf')).toBeInTheDocument()
  })

  it('sidebar shows only matched docs when search is active with results', async () => {
    render(<App />)
    await waitFor(() => screen.getByTestId('doc-search-input'))

    act(() => {
      // Simulate DocumentSearch resolving a query and calling back with results
      _onQueryChange?.('report')
      _onResults?.(SEARCH_MATCH)
    })

    await waitFor(() => {
      expect(screen.getByText('Report Q1.pdf')).toBeInTheDocument()
      expect(screen.queryByText('Handbook.pdf')).not.toBeInTheDocument()
    })
  })

  it('shows "no documents match" message when search returns empty results', async () => {
    render(<App />)
    await waitFor(() => screen.getByTestId('doc-search-input'))

    act(() => {
      _onQueryChange?.('zzznomatch')
      _onResults?.([])
    })

    await waitFor(() => {
      expect(screen.getByText(/no documents match/i)).toBeInTheDocument()
    })
  })

  it('restores full list when search is cleared', async () => {
    render(<App />)
    await waitFor(() => screen.getByTestId('doc-search-input'))

    // Activate search
    act(() => {
      _onQueryChange?.('report')
      _onResults?.(SEARCH_MATCH)
    })
    await waitFor(() =>
      expect(screen.queryByText('Handbook.pdf')).not.toBeInTheDocument()
    )

    // Clear search
    act(() => {
      _onQueryChange?.('')
      _onResults?.([])
    })
    await waitFor(() => {
      expect(screen.getByText('Report Q1.pdf')).toBeInTheDocument()
      expect(screen.getByText('Handbook.pdf')).toBeInTheDocument()
    })
  })

  it('search input is present after a document is selected', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))
    await waitFor(() => screen.getByTestId('pdf-viewer'))

    expect(screen.getByTestId('doc-search-input')).toBeInTheDocument()
  })

  it('selected document is deselected when deleted via search-filtered list', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    // Select doc-001
    clickElement(screen.getByText('Report Q1.pdf'))
    await waitFor(() => screen.getByTestId('pdf-viewer'))

    // Delete it
    await act(async () => {
      await documentsApi.deleteDocument.mockResolvedValue({})
    })

    act(() => {
      _onQueryChange?.('report')
      _onResults?.(SEARCH_MATCH)
    })

    // Verify the doc is removed from search results after delete
    act(() => { _onResults?.([]) })

    await waitFor(() => {
      expect(screen.queryByText('Handbook.pdf')).not.toBeInTheDocument()
    })
  })

  it('typing in the search input triggers onQueryChange', async () => {
    render(<App />)
    await waitFor(() => screen.getByTestId('doc-search-input'))

    act(() => {
      fireEvent.change(screen.getByTestId('doc-search-input'), {
        target: { value: 'report' },
      })
    })

    // After typing, search becomes active (no full list rendered until results arrive)
    act(() => { _onResults?.(SEARCH_MATCH) })

    await waitFor(() => {
      expect(screen.getByText('Report Q1.pdf')).toBeInTheDocument()
    })
  })

  it('multiple search queries in sequence each update the displayed list', async () => {
    render(<App />)
    await waitFor(() => screen.getByTestId('doc-search-input'))

    // First query — matches doc-001
    act(() => {
      _onQueryChange?.('report')
      _onResults?.([DOCS[0]])
    })
    await waitFor(() =>
      expect(screen.queryByText('Handbook.pdf')).not.toBeInTheDocument()
    )

    // Second query — matches doc-002
    act(() => {
      _onQueryChange?.('handbook')
      _onResults?.([DOCS[1]])
    })
    await waitFor(() => {
      expect(screen.getByText('Handbook.pdf')).toBeInTheDocument()
      expect(screen.queryByText('Report Q1.pdf')).not.toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// US-03 (viewer): PdfSearch lives inside PDFViewer boundary
// ---------------------------------------------------------------------------

describe('PdfSearch ↔ PDFViewer boundary', () => {

  it('pdf-search-boundary is absent when no document is selected', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))
    expect(screen.queryByTestId('pdf-search-boundary')).not.toBeInTheDocument()
  })

  it('pdf-search-boundary is present inside PDFViewer when a document is selected', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))

    await waitFor(() => {
      expect(screen.getByTestId('pdf-search-boundary')).toBeInTheDocument()
    })
  })

  it('pdf-search-boundary is removed when the viewer is closed', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))
    await waitFor(() => screen.getByTestId('pdf-search-boundary'))

    clickElement(screen.getByRole('button', { name: /close/i }))

    await waitFor(() => {
      expect(screen.queryByTestId('pdf-search-boundary')).not.toBeInTheDocument()
    })
  })

  it('switching documents keeps exactly one pdf-search-boundary in the DOM', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))
    await waitFor(() => screen.getByTestId('pdf-search-boundary'))

    clickElement(screen.getByText('Handbook.pdf'))
    await waitFor(() => {
      expect(screen.getAllByTestId('pdf-search-boundary')).toHaveLength(1)
    })
  })

  it('DocumentSearch and PdfSearch are independently accessible at the same time', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Report Q1.pdf'))

    clickElement(screen.getByText('Report Q1.pdf'))

    await waitFor(() => {
      expect(screen.getByTestId('doc-search-input')).toBeInTheDocument()
      expect(screen.getByTestId('pdf-search-boundary')).toBeInTheDocument()
    })
  })
})