import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import 'dayjs/locale/zh-cn'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#2563EB',
          borderRadius: 6,
          controlHeight: 32,
          fontSize: 13,
          colorText: '#1F2937',
          colorBorder: '#D9DEE7',
        },
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>
)
