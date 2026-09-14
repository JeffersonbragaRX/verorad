import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ToastProvider } from './components/Toast'
import { Overview } from './pages/Overview'
import { Coverage } from './pages/Coverage'
import { Concepts } from './pages/Concepts'
import { Associations } from './pages/Associations'
import { Physicians } from './pages/Physicians'
import { UnmodeledTail } from './pages/UnmodeledTail'
import { Library } from './pages/Library'
import { Compiler } from './pages/Compiler'
import { ReviewQueue } from './pages/ReviewQueue'

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="cobertura" element={<Coverage />} />
            <Route path="conceitos" element={<Concepts />} />
            <Route path="associacoes" element={<Associations />} />
            <Route path="medicos" element={<Physicians />} />
            <Route path="cauda" element={<UnmodeledTail />} />
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
