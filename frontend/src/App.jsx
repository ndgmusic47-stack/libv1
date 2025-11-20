import { Routes, Route } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import AppPage from './pages/AppPage';
import PricingPage from './pages/PricingPage';
import ProtectedRoute from './components/ProtectedRoute';
import BillingSuccess from './components/BillingSuccess';
import BillingCancel from './components/BillingCancel';

function App() {
  return (
    <Routes>
      <Route path="/" element={<LoginPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/pricing" element={<PricingPage />} />
      <Route path="/app" element={<AppPage />} />
      <Route path="/billing/success" element={<BillingSuccess />} />
      <Route path="/billing/cancel" element={<BillingCancel />} />
    </Routes>
  );
}

export default App;