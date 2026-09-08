import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ToastProvider } from './components/Toast'
import { Dashboard } from './pages/Dashboard'
import { Library } from './pages/Library'
import { Compiler } from './pages/Compiler'
import { ReviewQueue } from './pages/ReviewQueue'

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="biblioteca" element={<Library />} />
            <Route path="biblioteca/:id" element={<Library />} />
            <Route path="laudo" element={<Compiler />} />
            <Route path="revisao" element={<ReviewQueue />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  )
}
