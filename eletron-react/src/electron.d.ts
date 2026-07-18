export {}

declare global {
  interface Window {
    electronClipboard?: {
      writeImage: (dataUrl: string) => Promise<{ success: boolean; message?: string }>
    }
  }
}
