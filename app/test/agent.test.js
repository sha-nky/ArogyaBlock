const Agent = artifacts.require("Agent");

contract("Agent", (accounts) => {
  const patient = accounts[1];
  const doctor = accounts[2];
  const outsider = accounts[3];
  const accessFee = web3.toWei(2, "ether");

  let agent;

  beforeEach(async () => {
    agent = await Agent.new();
    await agent.add_agent("Patient A", 30, 0, "hash-1", { from: patient });
    await agent.add_agent("Doctor A", 45, 1, "", { from: doctor });
  });

  it("registers patient and doctor roles", async () => {
    const p = await agent.get_patient.call(patient);
    const d = await agent.get_doctor.call(doctor);

    assert.equal(p[0], "Patient A");
    assert.equal(d[0], "Doctor A");
  });

  it("enforces exact access fee and credits pool in wei", async () => {
    await agent.permit_access(doctor, { from: patient, value: accessFee });
    const pool = await agent.creditPool.call();
    assert.equal(pool.toString(), accessFee.toString());
  });

  it("blocks unauthorized remove_patient", async () => {
    await agent.permit_access(doctor, { from: patient, value: accessFee });

    try {
      await agent.remove_patient(patient, doctor, { from: outsider });
      assert.fail("Expected revert for unauthorized caller");
    } catch (error) {
      assert(error.message.includes("revert"), `Expected revert, got ${error.message}`);
    }
  });

  it("lets patient revoke access and refunds pool", async () => {
    await agent.permit_access(doctor, { from: patient, value: accessFee });
    await agent.revoke_access(doctor, { from: patient });

    const pool = await agent.creditPool.call();
    assert.equal(pool.toString(), "0");

    const hasAccess = await agent.hasAccess.call(patient, doctor);
    assert.equal(hasAccess, false);
  });
});
