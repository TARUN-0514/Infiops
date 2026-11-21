// Copies microphone samples to the page in small chunks (used by NEXUS voice).
class NexusTap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("nexus-tap", NexusTap);
