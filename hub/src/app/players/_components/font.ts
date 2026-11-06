import { Big_Shoulders } from "next/font/google";

/** The record pages' display face: tall, narrow and built for big numerals. */
export const recordDisplay = Big_Shoulders({
  subsets: ["latin"],
  variable: "--font-record",
  weight: ["600", "800"],
  display: "swap",
});
