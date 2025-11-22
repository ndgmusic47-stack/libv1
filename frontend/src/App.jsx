import { Routes, Route } from 'react-router-dom';
import AppPage from './pages/AppPage';
import PricingPage from './pages/PricingPage';
import BillingSuccess from './components/BillingSuccess';
import BillingCancel from './components/BillingCancel';

function App() {
  return (
    <Routes>
      <Route path="/" element={<AppPage />} />
      <Route path="/app" element={<AppPage />} />
      <Route path="/pricing" element={<PricingPage />} />
      <Route path="/billing/success" element={<BillingSuccess />} />
      <Route path="/billing/cancel" element={<BillingCancel />} />
    </Routes>
  );
}

export default App;