"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "../../../contexts/AuthContext";

function ManagerCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setManagerToken } = useAuth();

  useEffect(() => {
    const handleCallback = async () => {
      const token = searchParams.get("token");
      const error = searchParams.get("error");

      if (error) {
        console.error("Manager OAuth error:", error);
        router.push("/login?error=manager_auth_failed");
        return;
      }

      if (token) {
        // Store manager token
        localStorage.setItem("manager_token", token);
        setManagerToken(token);
        
        // Redirect to manager page
        router.push("/manager");
      } else {
        router.push("/login");
      }
    };

    handleCallback();
  }, [searchParams, router, setManagerToken]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center">
        <h2 className="text-2xl font-semibold text-gray-900 mb-2">
          Authenticating with Manager...
        </h2>
        <p className="text-gray-600">Please wait while we complete the authentication.</p>
      </div>
    </div>
  );
}

export default function ManagerCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <h2 className="text-2xl font-semibold text-gray-900 mb-2">
            Loading...
          </h2>
        </div>
      </div>
    }>
      <ManagerCallbackContent />
    </Suspense>
  );
}