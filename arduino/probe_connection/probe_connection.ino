const int probePin = 2;

void setup() {
  Serial.begin(9600);
  pinMode(probePin, INPUT_PULLUP);
}

void loop() {
  if (digitalRead(probePin) == LOW) {
    Serial.println("KAPCSOLAT");
    delay(300);
  }
}
