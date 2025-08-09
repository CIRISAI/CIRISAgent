// CIRIS TypeScript SDK Version Information
// This file is auto-updated during build

export const SDK_VERSION = {
  version: '1.3.3-beta',
  buildDate: new Date().toISOString(),
  gitHash: process.env.NEXT_PUBLIC_GIT_HASH || 'development',
  gitBranch: process.env.NEXT_PUBLIC_GIT_BRANCH || 'main',
}

export const getSDKVersion = () => SDK_VERSION.version
export const getSDKBuildInfo = () => SDK_VERSION
