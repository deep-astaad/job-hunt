"use client";

import { createContext, useContext, useState, useEffect } from "react";
import { useProfiles } from "@/hooks/useProfiles";

interface ProfileContextValue {
  profileId: string;
  setProfileId: (id: string) => void;
}

const ProfileContext = createContext<ProfileContextValue>({
  profileId: "",
  setProfileId: () => {},
});

export function ProfileProvider({ children }: { children: React.ReactNode }) {
  const { data } = useProfiles();
  const [profileId, setProfileId] = useState("");

  // Set default once profiles load
  useEffect(() => {
    if (!profileId && data?.profiles?.[0]?.id) {
      setProfileId(data.profiles[0].id);
    }
  }, [data, profileId]);

  return (
    <ProfileContext.Provider value={{ profileId, setProfileId }}>
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile() {
  return useContext(ProfileContext);
}
