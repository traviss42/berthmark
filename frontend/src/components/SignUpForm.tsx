import React, { useState } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Lock, Mail, User as UserIcon, AlertCircle, Loader2 } from 'lucide-react';

export interface SignUpFormProps {
  onSuccess?: () => void;
  onSwitchToLogin?: () => void;
  className?: string;
}

export const SignUpForm: React.FC<SignUpFormProps> = ({
  onSuccess,
  onSwitchToLogin,
  className = '',
}) => {
  const { register } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = email.trim();
    if (!cleanEmail || !password) {
      setErrorMessage('Please enter both email and password.');
      return;
    }

    setSubmitting(true);
    setErrorMessage(null);

    try {
      await register(name.trim(), cleanEmail, password);
      if (onSuccess) {
        onSuccess();
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object') {
        const errorObj = err as { statusCode?: number; message?: string };
        if (errorObj.statusCode === 409) {
          setErrorMessage(errorObj.message || 'Email already registered. Please sign in instead.');
        } else if (!errorObj.statusCode || errorObj.statusCode >= 500) {
          setErrorMessage('Connectivity failure. Unable to reach server.');
        } else {
          setErrorMessage(errorObj.message || 'Registration failed. Please check your details.');
        }
      } else {
        setErrorMessage('Connectivity failure. Unable to reach server.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={`bg-white rounded-xl shadow-sm border border-slate-200 p-6 ${className}`}>
      <div className="mb-5">
        <h2 className="text-lg font-bold text-slate-900">Create Berthmark Account</h2>
        <p className="text-xs text-slate-500 mt-1">
          Sign up to manage custom port watchlists and monitor real-time navigational risks.
        </p>
      </div>

      {errorMessage && (
        <div
          role="alert"
          data-testid="signup-error-alert"
          className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2.5 text-xs text-red-700"
        >
          <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
          <div className="flex-1 font-medium">{errorMessage}</div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <div>
          <label htmlFor="signup-name" className="block text-xs font-semibold text-slate-700 mb-1">
            Full Name
          </label>
          <div className="relative">
            <UserIcon className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              id="signup-name"
              data-testid="signup-name"
              type="text"
              disabled={submitting}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Captain Jack Aubrey"
              className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-slate-50 disabled:text-slate-400"
            />
          </div>
        </div>

        <div>
          <label htmlFor="signup-email" className="block text-xs font-semibold text-slate-700 mb-1">
            Email address
          </label>
          <div className="relative">
            <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              id="signup-email"
              data-testid="signup-email"
              type="email"
              required
              disabled={submitting}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="captain@fleet.com"
              className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-slate-50 disabled:text-slate-400"
            />
          </div>
        </div>

        <div>
          <label htmlFor="signup-password" className="block text-xs font-semibold text-slate-700 mb-1">
            Password
          </label>
          <div className="relative">
            <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              id="signup-password"
              data-testid="signup-password"
              type="password"
              required
              disabled={submitting}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-slate-50 disabled:text-slate-400"
            />
          </div>
        </div>

        <button
          type="submit"
          data-testid="signup-submit"
          disabled={submitting}
          className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-medium text-sm rounded-lg transition-colors flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed shadow-sm"
        >
          {submitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Creating account...</span>
            </>
          ) : (
            <span>Create Account</span>
          )}
        </button>

        {onSwitchToLogin && (
          <div className="pt-2 text-center text-xs text-slate-500">
            Already have an account?{' '}
            <button
              type="button"
              data-testid="switch-to-login"
              onClick={onSwitchToLogin}
              className="font-semibold text-blue-600 hover:text-blue-800 underline cursor-pointer"
            >
              Sign In
            </button>
          </div>
        )}
      </form>
    </div>
  );
};
