pragma solidity ^0.5.1;
 
 contract Agent {
    
    uint256 private constant ACCESS_FEE = 2 ether;

     struct patient {
         string name;
        uint256 age;
         address[] doctorAccessList;
        uint256[] diagnosis;
         string record;
     }
    

     struct doctor {
         string name;
        uint256 age;
         address[] patientAccessList;
     }

    uint256 public creditPool;
 
     address[] public patientList;
     address[] public doctorList;
 
     mapping (address => patient) patientInfo;
     mapping (address => doctor) doctorInfo;
     mapping (address => address) Empty;    
 
    event AgentAdded(address indexed agent, uint256 designation, string name, uint256 age);
    event AccessPermitted(address indexed patientAddr, address indexed doctorAddr, uint256 valueWei);
    event AccessRevoked(address indexed patientAddr, address indexed doctorAddr, uint256 valueWei);
    event RecordHashUpdated(address indexed patientAddr, string recordHash, address indexed updatedBy);
    event InsuranceClaimProcessed(address indexed patientAddr, address indexed doctorAddr, uint256 diagnosis);

    modifier onlyPatient(address addr) {
        require(bytes(patientInfo[addr].name).length > 0, "Patient not registered");
        _;
    }

    modifier onlyDoctor(address addr) {
        require(bytes(doctorInfo[addr].name).length > 0, "Doctor not registered");
        _;
    }

    modifier onlyLinked(address paddr, address daddr) {
        require(hasAccess(paddr, daddr), "Patient-doctor access link missing");
        _;
    }
 
    function add_agent(string memory _name, uint256 _age, uint256 _designation, string memory _hash) public returns(string memory){
         address addr = msg.sender;        
        require(bytes(_name).length > 0, "Name required");
        require(_age > 0, "Age required");
        require(bytes(patientInfo[addr].name).length == 0 && bytes(doctorInfo[addr].name).length == 0, "Already registered");

         if(_designation == 0){
            patient storage p = patientInfo[addr];
             p.name = _name;
             p.age = _age;
             p.record = _hash;
            patientList.push(addr);
            emit AgentAdded(addr, _designation, _name, _age);
            emit RecordHashUpdated(addr, _hash, msg.sender);
             return _name;
         }

        if (_designation == 1){
            doctor storage d = doctorInfo[addr];
            d.name = _name;
            d.age = _age;
            doctorList.push(addr);
            emit AgentAdded(addr, _designation, _name, _age);
             return _name;


        }

        revert("Invalid designation");
     }
 
 
    function get_patient(address addr) view public returns (string memory , uint256, uint256[] memory , address, string memory ){
         return (patientInfo[addr].name, patientInfo[addr].age, patientInfo[addr].diagnosis, Empty[addr], patientInfo[addr].record);
     }
 
    function get_doctor(address addr) view public returns (string memory , uint256){
         return (doctorInfo[addr].name, doctorInfo[addr].age);
     }

     function get_patient_doctor_name(address paddr, address daddr) view public returns (string memory , string memory ){
         return (patientInfo[paddr].name,doctorInfo[daddr].name);
     }
 
    function permit_access(address addr) payable public onlyPatient(msg.sender) onlyDoctor(addr) {
        require(msg.value == ACCESS_FEE, "Access fee must be 2 ether");
        require(!hasAccess(msg.sender, addr), "Access already granted");

        creditPool += ACCESS_FEE;

        doctorInfo[addr].patientAccessList.push(msg.sender);
        patientInfo[msg.sender].doctorAccessList.push(addr);

        emit AccessPermitted(msg.sender, addr, ACCESS_FEE);
     }
 
    function set_hash_public (address paddr, string memory _hash) public onlyPatient(paddr) {
        require(msg.sender == paddr || hasAccess(paddr, msg.sender), "Only patient or authorized doctor");
         set_hash(paddr, _hash);
     }
 
    // must be called by doctor linked to patient
    function insurance_claimm(address paddr, uint256 _diagnosis, string memory  _hash) public onlyDoctor(msg.sender) onlyPatient(paddr) onlyLinked(paddr, msg.sender) {
        require(creditPool >= ACCESS_FEE, "Insufficient credit pool");

        creditPool -= ACCESS_FEE;
        msg.sender.transfer(ACCESS_FEE);

        set_hash(paddr, _hash);
        remove_patient_internal(paddr, msg.sender);

        bool diagnosisFound = false;
        for(uint256 j = 0; j < patientInfo[paddr].diagnosis.length; j++){
            if(patientInfo[paddr].diagnosis[j] == _diagnosis) {
                diagnosisFound = true;
                break;
             }
         }
 
        if (!diagnosisFound) {
            patientInfo[paddr].diagnosis.push(_diagnosis);
        }

        emit InsuranceClaimProcessed(paddr, msg.sender, _diagnosis);
     }
 
    function remove_element_in_array(address[] storage arrayData, address addr) internal
     {
        bool check = false;
        uint256 del_index = 0;
        for(uint256 i = 0; i < arrayData.length; i++){
            if(arrayData[i] == addr){
                 check = true;
                 del_index = i;
                break;
             }
         }
        require(check, "Address not found");

        if(arrayData.length > 1) {
            arrayData[del_index] = arrayData[arrayData.length - 1];
        }
        arrayData.length--;
    }

    function remove_patient(address paddr, address daddr) public onlyLinked(paddr, daddr) {
        require(
            msg.sender == paddr || msg.sender == daddr,
            "Only linked patient or doctor can remove"
        );

        remove_patient_internal(paddr, daddr);
     }
 
    function remove_patient_internal(address paddr, address daddr) internal {
         remove_element_in_array(doctorInfo[daddr].patientAccessList, paddr);
         remove_element_in_array(patientInfo[paddr].doctorAccessList, daddr);
     }    

    function hasAccess(address paddr, address daddr) public view returns (bool) {
        for (uint256 i = 0; i < doctorInfo[daddr].patientAccessList.length; i++) {
            if (doctorInfo[daddr].patientAccessList[i] == paddr) {
                return true;
            }
        }
        return false;
    }

     function get_accessed_doctorlist_for_patient(address addr) public view returns (address[] memory )
    {
        return patientInfo[addr].doctorAccessList;
     }

     function get_accessed_patientlist_for_doctor(address addr) public view returns (address[] memory )
     {
         return doctorInfo[addr].patientAccessList;
     }

    function revoke_access(address daddr) public onlyPatient(msg.sender) onlyDoctor(daddr) onlyLinked(msg.sender, daddr){
        require(creditPool >= ACCESS_FEE, "Insufficient credit pool");

        remove_patient_internal(msg.sender,daddr);
        creditPool -= ACCESS_FEE;
        msg.sender.transfer(ACCESS_FEE);

        emit AccessRevoked(msg.sender, daddr, ACCESS_FEE);
     }
 
     function get_patient_list() public view returns(address[] memory ){
         return patientList;
     }
 
     function get_doctor_list() public view returns(address[] memory ){
         return doctorList;
     }
 
     function get_hash(address paddr) public view returns(string memory ){
         return patientInfo[paddr].record;
     }
 
     function set_hash(address paddr, string memory _hash) internal {
         patientInfo[paddr].record = _hash;
         emit RecordHashUpdated(paddr, _hash, msg.sender);
     }
 }
