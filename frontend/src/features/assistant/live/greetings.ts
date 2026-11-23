import type { LiveLanguage, LivePreferences } from './locale';

export const LIVE_GREETINGS = {
  vi: {
    female: [
      require('../../../../assets/live-greetings/vi-female-1.mp3'),
      require('../../../../assets/live-greetings/vi-female-2.mp3'),
      require('../../../../assets/live-greetings/vi-female-3.mp3'),
      require('../../../../assets/live-greetings/vi-female-4.mp3'),
      require('../../../../assets/live-greetings/vi-female-5.mp3'),
    ],
    male: [
      require('../../../../assets/live-greetings/vi-male-1.mp3'),
      require('../../../../assets/live-greetings/vi-male-2.mp3'),
      require('../../../../assets/live-greetings/vi-male-3.mp3'),
      require('../../../../assets/live-greetings/vi-male-4.mp3'),
      require('../../../../assets/live-greetings/vi-male-5.mp3'),
    ],
  },
  en: {
    female: [
      require('../../../../assets/live-greetings/en-female-1.mp3'),
      require('../../../../assets/live-greetings/en-female-2.mp3'),
      require('../../../../assets/live-greetings/en-female-3.mp3'),
      require('../../../../assets/live-greetings/en-female-4.mp3'),
      require('../../../../assets/live-greetings/en-female-5.mp3'),
    ],
    male: [
      require('../../../../assets/live-greetings/en-male-1.mp3'),
      require('../../../../assets/live-greetings/en-male-2.mp3'),
      require('../../../../assets/live-greetings/en-male-3.mp3'),
      require('../../../../assets/live-greetings/en-male-4.mp3'),
      require('../../../../assets/live-greetings/en-male-5.mp3'),
    ],
  },
} satisfies Record<LiveLanguage, Record<LivePreferences['voice'], number[]>>;

export class GreetingRotation {
  private remaining: Partial<Record<LiveLanguage, number[]>> = {};
  private last: Partial<Record<LiveLanguage, number>> = {};

  take({ language, voice }: LivePreferences) {
    const clips = LIVE_GREETINGS[language][voice];
    let variants = this.remaining[language];
    if (!variants?.length) {
      variants = clips.map((_, index) => index);
      for (let i = variants.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [variants[i], variants[j]] = [variants[j]!, variants[i]!];
      }
      const first = variants[0];
      if (first !== undefined && first === this.last[language]) variants.push(variants.shift()!);
      this.remaining[language] = variants;
    }
    const index = variants.shift()!;
    this.last[language] = index;
    return clips[index];
  }
}
