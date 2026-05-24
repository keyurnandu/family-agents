/**
 * US-02 — PDF Browser Rendering with PDF.js
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import PDFViewer from '../components/PDFViewer/PDFViewer';

vi.mock('../components/PDFViewer/PdfSearch', () => ({
  default: () => null,
}));

function clickElement(el) {
  act(() => { fireEvent.click(el); });
}

const MOCK_TOTAL_PAGES = 3;

const { mockPage, mockPdfDoc } = vi.hoisted(() => {
  const mockPage = {
    getViewport: vi.fn(() => ({ width: 800, height: 600, scale: 1 })),
    render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
  };
  const mockPdfDoc = {
    numPages: 3,
    getPage: vi.fn(() => Promise.resolve(mockPage)),
  };
  return { mockPage, mockPdfDoc };
});

vi.mock('pdfjs-dist', () => ({
  getDocument: vi.fn(() => ({
    promise: Promise.resolve(mockPdfDoc),
  })),
  GlobalWorkerOptions: {
    workerSrc: '',
  },
}));

const TEST_PDF_URL = '/uploads/test-document.pdf';

function renderViewer(props = {}) {
  return render(<PDFViewer url={TEST_PDF_URL} {...props} />);
}

afterEach(cleanup);

describe('US-02 — Render on mount', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPage.render.mockReturnValue({ promise: Promise.resolve(), cancel: vi.fn() });
    mockPage.getViewport.mockReturnValue({ width: 800, height: 600, scale: 1 });
    mockPdfDoc.getPage.mockResolvedValue(mockPage);
  });

  test('TC-02-01: renders a canvas element for PDF display', async () => {
    renderViewer();
    await waitFor(() => expect(document.querySelector('canvas')).toBeInTheDocument());
  });

  test('TC-02-02: calls pdfjs.getDocument with the provided URL on mount', async () => {
    const pdfjs = await import('pdfjs-dist');
    pdfjs.getDocument.mockReturnValue({ promise: Promise.resolve(mockPdfDoc) });
    renderViewer();
    await waitFor(() => expect(pdfjs.getDocument).toHaveBeenCalledTimes(1));
    expect(pdfjs.getDocument).toHaveBeenCalledWith(TEST_PDF_URL);
  });

  test('TC-02-03: shows a loading indicator before PDF is ready', async () => {
    const pdfjs = await import('pdfjs-dist');
    let resolveLoad;
    const loadPromise = new Promise((resolve) => { resolveLoad = resolve; });
    pdfjs.getDocument.mockReturnValueOnce({ promise: loadPromise });

    renderViewer();
    expect(screen.getByRole('status')).toBeInTheDocument();

    await act(async () => {
      resolveLoad(mockPdfDoc);
      await loadPromise;
    });
  });

  test('TC-02-04: hides the loading indicator once PDF has loaded', async () => {
    renderViewer();
    await waitFor(() =>
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
    );
  });

  test('TC-02-05: renders the first page (page 1) automatically on mount', async () => {
    renderViewer();
    await waitFor(() => expect(mockPdfDoc.getPage).toHaveBeenCalledWith(1));
  });

  test('TC-02-06: displays total page count after load', async () => {
    renderViewer();
    await waitFor(() =>
      expect(screen.getByText(/of\s*3/i)).toBeInTheDocument()
    );
  });
});

describe('US-02 — Page counter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPage.render.mockReturnValue({ promise: Promise.resolve(), cancel: vi.fn() });
    mockPage.getViewport.mockReturnValue({ width: 800, height: 600, scale: 1 });
    mockPdfDoc.getPage.mockResolvedValue(mockPage);
  });

  test('TC-02-07: displays "Page 1 of 3" on initial render', async () => {
    renderViewer();
    await waitFor(() =>
      expect(screen.getByText(/page\s*1\s*of\s*3/i)).toBeInTheDocument()
    );
  });

  test('TC-02-08: updates page counter when navigating to page 2', async () => {
    renderViewer();
    await waitFor(() => screen.getByText(/page\s*1\s*of\s*3/i));

    clickElement(screen.getByRole('button', { name: /next/i }));

    await waitFor(() =>
      expect(screen.getByText(/page\s*2\s*of\s*3/i)).toBeInTheDocument()
    );
  });
});

describe('US-02 — Next page navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPage.render.mockReturnValue({ promise: Promise.resolve(), cancel: vi.fn() });
    mockPage.getViewport.mockReturnValue({ width: 800, height: 600, scale: 1 });
    mockPdfDoc.getPage.mockResolvedValue(mockPage);
  });

  test('TC-02-09: renders a "Next" button', async () => {
    renderViewer();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument()
    );
  });

  test('TC-02-10: clicking Next loads page 2', async () => {
    renderViewer();
    await waitFor(() => screen.getByText(/page\s*1\s*of\s*3/i));

    clickElement(screen.getByRole('button', { name: /next/i }));

    await waitFor(() => expect(mockPdfDoc.getPage).toHaveBeenCalledWith(2));
  });

  test('TC-02-11: clicking Next twice loads page 3', async () => {
    renderViewer();
    await waitFor(() => screen.getByText(/page\s*1\s*of\s*3/i));

    clickElement(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => screen.getByText(/page\s*2\s*of\s*3/i));

    clickElement(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(mockPdfDoc.getPage).toHaveBeenCalledWith(3));
  });

  test('TC-02-12: Next button is disabled on the last page', async () => {
    renderViewer();
    await waitFor(() => screen.getByText(/page\s*1\s*of\s*3/i));

    clickElement(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => screen.getByText(/page\s*2\s*of\s*3/i));
    clickElement(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => screen.getByText(/page\s*3\s*of\s*3/i));

    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
  });
});

describe('US-02 — Previous page navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPage.render.mockReturnValue({ promise: Promise.resolve(), cancel: vi.fn() });
    mockPage.getViewport.mockReturnValue({ width: 800, height: 600, scale: 1 });
    mockPdfDoc.getPage.mockResolvedValue(mockPage);
  });

  test('TC-02-13: renders a "Previous" button', async () => {
    renderViewer();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /prev/i })).toBeInTheDocument()
    );
  });

  test('TC-02-14: Previous button is disabled on the first page', async () => {
    renderViewer();
    await waitFor(() => screen.getByText(/page\s*1\s*of\s*3/i));
    expect(screen.getByRole('button', { name: /prev/i })).toBeDisabled();
  });

  test('TC-02-15: clicking Next then Previous returns to page 1', async () => {
    renderViewer();
    await waitFor(() => screen.getByText(/page\s*1\s*of\s*3/i));

    clickElement(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => screen.getByText(/page\s*2\s*of\s*3/i));

    clickElement(screen.getByRole('button', { name: /prev/i }));
    await waitFor(() =>
      expect(screen.getByText(/page\s*1\s*of\s*3/i)).toBeInTheDocument()
    );
  });

  test('TC-02-16: Previous button re-calls getPage with the decremented page number', async () => {
    renderViewer();
    await waitFor(() => screen.getByText(/page\s*1\s*of\s*3/i));

    clickElement(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => screen.getByText(/page\s*2\s*of\s*3/i));

    vi.clearAllMocks();
    mockPage.render.mockReturnValue({ promise: Promise.resolve(), cancel: vi.fn() });
    mockPage.getViewport.mockReturnValue({ width: 800, height: 600, scale: 1 });
    mockPdfDoc.getPage.mockResolvedValue(mockPage);
    clickElement(screen.getByRole('button', { name: /prev/i }));

    await waitFor(() => expect(mockPdfDoc.getPage).toHaveBeenCalledWith(1));
  });

  test('TC-02-17: Previous button is re-enabled after navigating to page 2', async () => {
    renderViewer();
    await waitFor(() => screen.getByText(/page\s*1\s*of\s*3/i));

    clickElement(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => screen.getByText(/page\s*2\s*of\s*3/i));

    expect(screen.getByRole('button', { name: /prev/i })).not.toBeDisabled();
  });
});

describe('US-02 — Error handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPage.render.mockReturnValue({ promise: Promise.resolve(), cancel: vi.fn() });
    mockPage.getViewport.mockReturnValue({ width: 800, height: 600, scale: 1 });
    mockPdfDoc.getPage.mockResolvedValue(mockPage);
  });

  test('TC-02-18: displays an error message when PDF fails to load', async () => {
    const pdfjs = await import('pdfjs-dist');
    const rejection = Promise.reject(new Error('Failed to fetch PDF'));
    rejection.catch(() => {});
    pdfjs.getDocument.mockReturnValueOnce({ promise: rejection });

    renderViewer();

    await waitFor(() =>
      expect(screen.getByRole('alert')).toBeInTheDocument()
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/failed|error|could not load/i);
  });

  test('TC-02-19: does not render canvas when PDF fails to load', async () => {
    const pdfjs = await import('pdfjs-dist');
    const rejection = Promise.reject(new Error('Network error'));
    rejection.catch(() => {});
    pdfjs.getDocument.mockReturnValueOnce({ promise: rejection });

    renderViewer();
    await waitFor(() => screen.getByRole('alert'));

    expect(document.querySelector('canvas')).not.toBeInTheDocument();
  });
});

describe('US-02 — URL prop change', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPage.render.mockReturnValue({ promise: Promise.resolve(), cancel: vi.fn() });
    mockPage.getViewport.mockReturnValue({ width: 800, height: 600, scale: 1 });
    mockPdfDoc.getPage.mockResolvedValue(mockPage);
  });

  test('TC-02-20: reloads PDF when the url prop changes', async () => {
    const pdfjs = await import('pdfjs-dist');
    pdfjs.getDocument.mockReturnValue({ promise: Promise.resolve(mockPdfDoc) });
    const { rerender } = renderViewer({ url: '/uploads/doc-a.pdf' });
    await waitFor(() => expect(pdfjs.getDocument).toHaveBeenCalledWith('/uploads/doc-a.pdf'));

    vi.clearAllMocks();
    mockPage.render.mockReturnValue({ promise: Promise.resolve(), cancel: vi.fn() });
    mockPage.getViewport.mockReturnValue({ width: 800, height: 600, scale: 1 });
    mockPdfDoc.getPage.mockResolvedValue(mockPage);
    pdfjs.getDocument.mockReturnValue({ promise: Promise.resolve(mockPdfDoc) });
    rerender(<PDFViewer url="/uploads/doc-b.pdf" />);

    await waitFor(() => expect(pdfjs.getDocument).toHaveBeenCalledWith('/uploads/doc-b.pdf'));
  });

  test('TC-02-21: resets to page 1 when the url prop changes', async () => {
    const { rerender } = renderViewer({ url: '/uploads/doc-a.pdf' });
    await waitFor(() => screen.getByText(/page\s*1\s*of\s*3/i));

    clickElement(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => screen.getByText(/page\s*2\s*of\s*3/i));

    rerender(<PDFViewer url="/uploads/doc-b.pdf" />);

    await waitFor(() =>
      expect(screen.getByText(/page\s*1\s*of\s*3/i)).toBeInTheDocument()
    );
  });
});